"""命令执行器 — 权限门禁 + 高危确认 + 进程隔离"""
import subprocess
import uuid
import time
import re
from dataclasses import dataclass, field

from ....contracts.types import RiskLevel, ToolResult


# 高危命令正则（入口拦截）
BLOCKED_PATTERNS = [
    r"\brm\s+.*-rf\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bchmod\s+.*777\b",
    r">\s*/dev/sda",
    r"\bformat\b",
]

# 敏感路径（告警但不阻塞）
SENSITIVE_PATHS = [
    "/etc/shadow",
    "/root/.ssh",
    "/boot",
    "/etc/passwd",
    "/etc/sudoers",
]


@dataclass
class ExecutionRequest:
    cmd: list[str]
    risk_level: RiskLevel
    needs_confirmation: bool = False
    dry_run_cmd: list[str] | None = None
    capability: str = "management"
    timeout: int = 30


def _check_intent(cmd_str: str) -> tuple[bool, str]:
    """入口规则检查：高危命令直接拦截"""
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd_str, re.IGNORECASE):
            return False, f"BLOCKED: 匹配高危模式 '{pattern}'"
    return True, ""


def _check_sensitive_paths(cmd_str: str) -> list[str]:
    """检测是否触碰敏感路径"""
    warnings = []
    for path in SENSITIVE_PATHS:
        if path in cmd_str:
            warnings.append(f"WARNING: 触碰到敏感路径 {path}")
    return warnings


def execute_command(req: ExecutionRequest) -> ToolResult:
    """执行命令，带权限校验"""
    audit_id = str(uuid.uuid4())
    cmd_str = " ".join(req.cmd)

    # 第 1 层：高危命令拦截
    ok, reason = _check_intent(cmd_str)
    if not ok:
        return ToolResult(success=False, data=None, audit_id=audit_id, error=reason)

    # 敏感路径告警
    warnings = _check_sensitive_paths(cmd_str)

    # 高危操作需确认
    if req.needs_confirmation:
        # 先 dry-run
        if req.dry_run_cmd:
            dr = subprocess.run(req.dry_run_cmd, capture_output=True, text=True, timeout=10)
            return ToolResult(
                success=True,
                data={"dry_run": dr.stdout.strip(), "warnings": warnings, "needs_confirmation": True},
                audit_id=audit_id,
                needs_confirmation=True,
            )
        return ToolResult(
            success=True,
            data={"warnings": warnings, "needs_confirmation": True},
            audit_id=audit_id,
            needs_confirmation=True,
        )

    # 实际执行
    try:
        result = subprocess.run(req.cmd, capture_output=True, text=True, timeout=req.timeout)
        return ToolResult(
            success=result.returncode == 0,
            data={"stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "rc": result.returncode,
                  "warnings": warnings},
            audit_id=audit_id,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, data=None, audit_id=audit_id, error=f"执行超时({req.timeout}s)")
    except FileNotFoundError:
        return ToolResult(success=False, data=None, audit_id=audit_id, error=f"命令未找到: {req.cmd[0]}")
