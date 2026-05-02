"""OpenAI 兼容 Provider — 适用于 Qwen / DeepSeek / Ollama。

使用 openai SDK，通过不同的 base_url 区分 provider。
SDK 延迟导入，仅在实际调用时加载。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..types import ReasonerRequest, ReasonerResponse, ToolCall, ToolDef

logger = logging.getLogger("gcode.reasoning.openai_compat")

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


class OpenAICompatProvider:
    """OpenAI 兼容 API Provider（Qwen / DeepSeek / Ollama）。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        name: str = "openai_compat",
        timeout: int = 30,
    ):
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._name = name
        self._timeout = timeout
        self._client: Any = None

    @property
    def name(self) -> str:
        return self._name

    def _ensure_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
                timeout=self._timeout,
            )
        return self._client

    async def complete(self, request: ReasonerRequest) -> ReasonerResponse:
        client = self._ensure_client()

        tools = [_to_openai_tool(t) for t in request.tools]
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(request.history)
        messages.append({"role": "user", "content": request.query})

        logger.debug("Calling %s/%s with %d tools", self._name, self._model, len(tools))

        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        return _parse_response(response, self._name, self._model)


def _to_openai_tool(t: ToolDef) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        },
    }


def _parse_response(response: Any, provider: str, model: str) -> ReasonerResponse:
    msg = response.choices[0].message

    text = msg.content or ""
    tool_calls: list[ToolCall] = []

    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(ToolCall(name=tc.function.name, arguments=args))

    usage = {}
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }

    return ReasonerResponse(
        text=text,
        tool_calls=tool_calls,
        provider=provider,
        model=model,
        usage=usage,
    )


# ── 工厂函数 ──


def create_qwen_provider(
    api_key: str, model: str = "qwen-plus", timeout: int = 30
) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=api_key,
        model=model,
        name="qwen",
        timeout=timeout,
    )


def create_deepseek_provider(
    api_key: str, model: str = "deepseek-chat", timeout: int = 30
) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url="https://api.deepseek.com/v1",
        api_key=api_key,
        model=model,
        name="deepseek",
        timeout=timeout,
    )


def create_ollama_provider(
    model: str = "qwen2.5:7b",
    base_url: str = "http://localhost:11434/v1",
    timeout: int = 60,
) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url=base_url,
        api_key="ollama",
        model=model,
        name="ollama",
        timeout=timeout,
    )
