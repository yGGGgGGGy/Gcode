"""Anthropic Claude Provider。

使用 anthropic SDK，tool 格式与 OpenAI 不同（input_schema / tool_use blocks）。
SDK 延迟导入，仅在实际调用时加载。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..types import ReasonerRequest, ReasonerResponse, ToolCall, ToolDef

logger = logging.getLogger("gcode.reasoning.anthropic")

SYSTEM_PROMPT = """你是 Gcode 智能运维助手，运行在麒麟OS上。
你的职责是通过调用工具来回答用户的运维问题。

可用工具覆盖：
- 系统信息查询（sys_info, ps_list, df_h, netstat, journalctl）
- 性能指标采集（cpu_usage, mem_usage, io_stat, disk_health）
- 服务管理（service_status, service_restart, pkg_install）

规则：
1. 优先使用工具获取实时数据，不要凭记忆回答
2. 如果一个问题需要多个工具，可以一次调用多个
3. 用中文回答，格式简洁明了
4. 对于高风险操作（重启服务、安装包），提醒用户需要确认
"""


class AnthropicProvider:
    """Anthropic Claude API Provider。"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        timeout: int = 30,
    ):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client: Any = None

    @property
    def name(self) -> str:
        return "claude"

    def _ensure_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self._api_key,
                timeout=self._timeout,
            )
        return self._client

    async def complete(self, request: ReasonerRequest) -> ReasonerResponse:
        client = self._ensure_client()

        tools = [_to_anthropic_tool(t) for t in request.tools]
        messages: list[dict[str, Any]] = []
        messages.extend(request.history)
        messages.append({"role": "user", "content": request.query})

        logger.debug("Calling %s with %d tools", self._model, len(tools))

        response = await client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
        )

        return _parse_response(response, self._model)


def _to_anthropic_tool(t: ToolDef) -> dict[str, Any]:
    return {
        "name": t.name,
        "description": t.description,
        "input_schema": t.parameters,
    }


def _parse_response(response: Any, model: str) -> ReasonerResponse:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(
                ToolCall(name=block.name, arguments=block.input)
            )

    usage = {}
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }

    return ReasonerResponse(
        text="\n".join(text_parts),
        tool_calls=tool_calls,
        provider="claude",
        model=model,
        usage=usage,
    )
