"""LLM Provider 抽象协议。"""
from __future__ import annotations

from typing import Protocol

from .types import ReasonerRequest, ReasonerResponse


class LLMProvider(Protocol):
    """支持 tool calling 的 LLM Provider 协议。"""

    @property
    def name(self) -> str: ...

    async def complete(self, request: ReasonerRequest) -> ReasonerResponse: ...
