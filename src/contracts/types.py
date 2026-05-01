"""m1↔dp1 接口类型定义。

m1 → dp1: SessionContext（经意图过滤后的安全上下文）
dp1 → m1: ToolCallRecord（执行记录，推入审计层）

与 dp1 侧 src/contracts/types.py 一一对应。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

RiskVerdict = Literal["safe", "unsafe", "needs-review", "error"]
RiskLevel = Literal["read_only", "read_write", "admin"]


@dataclass
class ToolResult:
    """Tool 执行结果，由 dp1 MCP Server 返回。"""

    success: bool
    data: dict[str, Any] | None = None
    audit_id: str = ""
    error: str | None = None
    needs_confirmation: bool = False


@dataclass
class SessionContext:
    """m1 → dp1: 意图过滤后构建的安全上下文。

    m1 完成意图分类后，将过滤后的可执行输入 + 风险评级打包发送给 dp1。
    """

    session_id: str
    filtered_input: str
    risk_score: float
    risk_verdict: RiskVerdict
    capability_set: list[str] = field(default_factory=list)
    reason: str = ""
    user_id: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "filtered_input": self.filtered_input,
            "risk_score": self.risk_score,
            "risk_verdict": self.risk_verdict,
            "capability_set": self.capability_set,
            "reason": self.reason,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
        }


@dataclass
class ToolCallRecord:
    """dp1 → m1: 单次Tool调用记录，推入审计层。

    dp1 每执行一个 Tool 生成一条记录，m1 审计层收集后写入 SQLite。
    """

    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    step_id: str = ""
    parent_step_id: str | None = None
    tool_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = "read_only"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCallRecord:
        return cls(
            audit_id=data.get("audit_id", str(uuid.uuid4())),
            session_id=data.get("session_id", ""),
            step_id=data.get("step_id", ""),
            parent_step_id=data.get("parent_step_id"),
            tool_name=data.get("tool_name", ""),
            params=data.get("params", {}),
            result=data.get("result", {}),
            risk_level=data.get("risk_level", "read_only"),
            timestamp=data.get("timestamp", ""),
        )
