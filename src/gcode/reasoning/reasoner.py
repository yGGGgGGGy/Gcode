"""推理编排器 — 调用 LLM → 解析 tool_calls → 执行 Tool → 返回结果。"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Protocol

from .tool_registry import get_tools
from .types import ReasonerRequest, ReasonerResponse, ToolCall

logger = logging.getLogger("gcode.reasoning")


class ToolExecutor(Protocol):
    """Tool 执行器协议。"""

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str: ...


class MCPToolExecutor:
    """通过直接调用 MCP Tool handler 函数来执行 Tool。

    不依赖 MCP Server 进程，直接导入并调用底层实现。
    """

    def __init__(self):
        self._handlers: dict[str, Any] | None = None

    def _load_handlers(self) -> dict[str, Any]:
        if self._handlers is None:
            from ..mcp.tools_readonly import (
                sys_info, ps_list, df_h, netstat, journalctl,
            )
            from ..mcp.tools_metrics import (
                cpu_usage, mem_usage, io_stat, disk_health,
            )
            from ..mcp.tools_management import (
                service_status, service_restart, pkg_install,
            )

            self._handlers = {
                "sys_info": sys_info,
                "ps_list": ps_list,
                "df_h": df_h,
                "netstat": netstat,
                "journalctl": journalctl,
                "cpu_usage": cpu_usage,
                "mem_usage": mem_usage,
                "io_stat": io_stat,
                "disk_health": disk_health,
                "service_status": service_status,
                "service_restart": service_restart,
                "pkg_install": pkg_install,
            }
        return self._handlers

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        handlers = self._load_handlers()
        handler = handlers.get(tool_name)
        if handler is None:
            return f"[error] Unknown tool: {tool_name}"

        try:
            # 过滤掉 handler 不接受的参数
            sig = inspect.signature(handler)
            valid_params = set(sig.parameters.keys())
            filtered = {k: v for k, v in arguments.items() if k in valid_params}

            result = await handler(**filtered)
            # result 是 list[TextContent]
            if isinstance(result, list):
                return "\n".join(tc.text for tc in result)
            return str(result)
        except Exception as e:
            logger.exception("Tool %s failed", tool_name)
            return f"[error] {tool_name} failed: {e}"


class Reasoner:
    """推理编排器：LLM 调用 → Tool 执行 → 结果汇总。"""

    def __init__(
        self,
        provider: Any,
        tool_executor: ToolExecutor | None = None,
        max_tool_rounds: int = 3,
    ):
        self._provider = provider
        self._executor = tool_executor or MCPToolExecutor()
        self._max_tool_rounds = max_tool_rounds

    async def reason(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
        allow_write: bool = False,
    ) -> ReasonerResponse:
        """完整推理循环：调 LLM → 执行 Tool → 再调 LLM → ..."""
        tools = get_tools(allow_write=allow_write)
        request = ReasonerRequest(query=query, tools=tools, history=history or [])

        last_response: ReasonerResponse | None = None

        for round_num in range(self._max_tool_rounds):
            logger.debug("Reasoner round %d/%d", round_num + 1, self._max_tool_rounds)

            response = await self._provider.complete(request)
            last_response = response

            if not response.tool_calls:
                # LLM 没有请求调用 Tool，推理结束
                break

            # 执行 Tool 调用
            tool_results: list[dict[str, str]] = []
            for tc in response.tool_calls:
                logger.info("Executing tool: %s(%s)", tc.name, tc.arguments)
                result = await self._executor.execute(tc.name, tc.arguments)
                tool_results.append({"tool": tc.name, "result": result})

            response.tool_results = tool_results

            # 将 Tool 结果加入 history，让 LLM 继续推理
            if round_num < self._max_tool_rounds - 1:
                # 构建 follow-up 请求
                new_history = list(request.history)
                new_history.append({"role": "user", "content": query})

                # 汇总 tool 结果给 LLM
                tool_summary_parts = []
                for tr in tool_results:
                    tool_summary_parts.append(f"[{tr['tool']}]\n{tr['result']}")
                tool_summary = "\n\n".join(tool_summary_parts)

                new_history.append({
                    "role": "assistant",
                    "content": response.text or f"我需要调用工具来回答这个问题。",
                })
                new_history.append({
                    "role": "user",
                    "content": f"工具执行结果：\n{tool_summary}\n\n请根据以上结果回答我的问题。",
                })

                request = ReasonerRequest(
                    query="",  # query 已在 history 中
                    tools=request.tools,
                    history=new_history,
                )

        if last_response is None:
            return ReasonerResponse(text="[error] 推理循环未执行", provider="none", model="none")

        return last_response
