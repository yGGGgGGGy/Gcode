"""工具调度器 — 直接调用工具，不走 MCP 协议。

安全层通过此类直接执行工具，绕过 stdio MCP Server。
"""
from __future__ import annotations

import subprocess
import platform
import socket
from typing import Any


def _safe_run(cmd: list[str], timeout: int = 10) -> dict:
    """安全执行命令，返回结果字典。"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "rc": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"命令超时 ({timeout}s)", "rc": -1}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": f"命令不存在: {cmd[0]}", "rc": -1}


# ===== 只读工具 =====

def sys_info() -> dict:
    info = {
        "hostname": socket.gethostname(),
        "kernel": platform.release(),
        "arch": platform.machine(),
        "os": platform.system(),
        "python": platform.python_version(),
    }
    try:
        r = subprocess.run(["cat", "/etc/kylin-release"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            info["kylin_release"] = r.stdout.strip()
    except Exception:
        pass
    return {"success": True, "stdout": str(info), "stderr": "", "rc": 0}


def ps_list() -> dict:
    return _safe_run(["ps", "aux", "--no-headers"])


def df_h() -> dict:
    return _safe_run(["df", "-h"])


def netstat() -> dict:
    return _safe_run(["ss", "-tulnp"])


def journalctl(service: str = "", lines: int = 50) -> dict:
    cmd = ["journalctl", "-n", str(lines), "--no-pager"]
    if service:
        cmd.extend(["-u", service])
    return _safe_run(cmd, timeout=15)


# ===== 指标工具 =====

def cpu_usage() -> dict:
    try:
        import psutil
        percent = psutil.cpu_percent(interval=1, percpu=False)
        per_cpu = psutil.cpu_percent(interval=0, percpu=True)
        return {"success": True, "stdout": str({"percent": percent, "per_cpu": per_cpu, "count": len(per_cpu)}), "stderr": "", "rc": 0}
    except ImportError:
        return _safe_run(["top", "-bn1", "-p1"])


def mem_usage() -> dict:
    try:
        import psutil
        m = psutil.virtual_memory()
        return {"success": True, "stdout": str({
            "total_gb": round(m.total / 1024**3, 2),
            "used_gb": round(m.used / 1024**3, 2),
            "available_gb": round(m.available / 1024**3, 2),
            "percent": m.percent,
        }), "stderr": "", "rc": 0}
    except ImportError:
        return _safe_run(["free", "-h"])


def io_stat() -> dict:
    return _safe_run(["iostat", "-x", "1", "1"])


def disk_health(device: str = "/dev/sda") -> dict:
    return _safe_run(["smartctl", "-H", device])


# ===== 管理工具 =====

def service_status(name: str) -> dict:
    return _safe_run(["systemctl", "status", name, "--no-pager"])


def service_restart(name: str, dry_run: bool = True) -> dict:
    if dry_run:
        return service_status(name)
    return _safe_run(["systemctl", "restart", name])


def pkg_install(name: str, dry_run: bool = True) -> dict:
    if dry_run:
        return _safe_run(["dnf", "info", name])
    return _safe_run(["dnf", "install", "-y", name], timeout=120)


# ===== 工具注册表 =====

TOOL_REGISTRY: dict[str, callable] = {
    "sys_info": lambda p: sys_info(),
    "ps_list": lambda p: ps_list(),
    "df_h": lambda p: df_h(),
    "netstat": lambda p: netstat(),
    "journalctl": lambda p: journalctl(service=p.get("service", ""), lines=p.get("lines", 50)),
    "cpu_usage": lambda p: cpu_usage(),
    "mem_usage": lambda p: mem_usage(),
    "io_stat": lambda p: io_stat(),
    "disk_health": lambda p: disk_health(device=p.get("device", "/dev/sda")),
    "service_status": lambda p: service_status(p.get("name", "")),
    "service_restart": lambda p: service_restart(p.get("name", ""), dry_run=p.get("dry_run", True)),
    "pkg_install": lambda p: pkg_install(p.get("name", ""), dry_run=p.get("dry_run", True)),
}

# 工具风险等级
TOOL_RISK: dict[str, str] = {
    "sys_info": "read_only",
    "ps_list": "read_only",
    "df_h": "read_only",
    "netstat": "read_only",
    "journalctl": "read_only",
    "cpu_usage": "read_only",
    "mem_usage": "read_only",
    "io_stat": "read_only",
    "disk_health": "read_only",
    "service_status": "read_only",
    "service_restart": "admin",
    "pkg_install": "admin",
}


def dispatch(tool_name: str, params: dict | None = None) -> dict:
    """调度工具执行。"""
    params = params or {}
    func = TOOL_REGISTRY.get(tool_name)
    if func is None:
        return {"success": False, "stdout": "", "stderr": f"未知工具: {tool_name}", "rc": -1}
    return func(params)
