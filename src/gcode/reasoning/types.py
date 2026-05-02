"""推理层数据类型 — Provider 无关的共享契约。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDef:
    """LLM function-calling 工具定义。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ReasonerRequest:
    """发送给 LLM Provider 的请求。"""

    query: str
    tools: list[ToolDef]
    history: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ToolCall:
    """从 LLM 响应中解析出的工具调用。"""

    name: str
    arguments: dict[str, Any]


@dataclass
class ReasonerResponse:
    """LLM Provider 返回的结果。"""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[dict[str, str]] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
