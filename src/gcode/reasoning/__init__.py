"""Gcode 推理层 — 多 Provider LLM 推理 + Tool 调用。"""
from __future__ import annotations

from typing import Any

from .reasoner import MCPToolExecutor, Reasoner
from .tool_registry import get_tools
from .types import ReasonerRequest, ReasonerResponse, ToolCall, ToolDef

__all__ = [
    "Reasoner",
    "MCPToolExecutor",
    "ReasonerRequest",
    "ReasonerResponse",
    "ToolCall",
    "ToolDef",
    "get_tools",
    "create_reasoner",
]


def create_reasoner(config: Any) -> Reasoner:
    """从 GcodeConfig 创建 Reasoner 实例。

    Args:
        config: GcodeConfig 实例，需要有 config.reasoner 属性。
    """
    rc = config.reasoner
    provider = _create_provider(rc)
    return Reasoner(
        provider=provider,
        max_tool_rounds=rc.max_tool_rounds,
    )


def _create_provider(rc: Any) -> Any:
    provider = rc.provider

    if provider == "qwen":
        from .providers.openai_compat import create_qwen_provider

        return create_qwen_provider(
            api_key=rc.api_key, model=rc.model, timeout=rc.timeout
        )

    if provider == "deepseek":
        from .providers.openai_compat import create_deepseek_provider

        return create_deepseek_provider(
            api_key=rc.api_key, model=rc.model, timeout=rc.timeout
        )

    if provider == "claude":
        from .providers.anthropic import AnthropicProvider

        return AnthropicProvider(
            api_key=rc.api_key, model=rc.model, timeout=rc.timeout
        )

    if provider == "ollama":
        from .providers.openai_compat import create_ollama_provider

        base_url = rc.base_url or "http://localhost:11434/v1"
        return create_ollama_provider(
            model=rc.model, base_url=base_url, timeout=rc.timeout
        )

    raise ValueError(f"Unknown provider: {provider!r}")
