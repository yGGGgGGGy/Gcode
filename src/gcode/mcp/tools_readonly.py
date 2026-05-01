"""只读感知工具 — 风险等级 LOW
系统信息查询，不改变任何状态。"""
import subprocess
import platform
import socket
from mcp.server import Server
from mcp.types import Tool, TextContent

from ....contracts.types import ToolResult, RiskLevel

RISK = "read_only"


def _safe_run(cmd: list[str], timeout: int = 10) -> ToolResult:
    """安全执行只读命令，捕获 stdout/stderr"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return ToolResult(
            success=result.returncode == 0,
            data={"stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "rc": result.returncode},
            audit_id="",
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, data=None, audit_id="", error=f"Command timed out after {timeout}s")


def register_readonly_tools(server: Server):
    @server.tool()
    async def sys_info() -> list[TextContent]:
        """获取系统基本信息：内核版本、主机名、架构、启动时间"""
        info = {
            "hostname": socket.gethostname(),
            "kernel": platform.release(),
            "arch": platform.machine(),
            "os": platform.system(),
            "python": platform.python_version(),
        }
        # 麒麟特有: 检查 Kylin 版本
        try:
            r = subprocess.run(["cat", "/etc/kylin-release"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                info["kylin_release"] = r.stdout.strip()
        except Exception:
            pass

        return [TextContent(type="text", text=str(info))]

    @server.tool()
    async def ps_list() -> list[TextContent]:
        """列出当前运行的进程信息"""
        r = _safe_run(["ps", "aux", "--no-headers"])
        return [TextContent(type="text", text=r.data.get("stdout", "") if r.success else (r.error or ""))]

    @server.tool()
    async def df_h() -> list[TextContent]:
        """查看磁盘使用情况"""
        r = _safe_run(["df", "-h"])
        return [TextContent(type="text", text=r.data.get("stdout", "") if r.success else (r.error or ""))]

    @server.tool()
    async def netstat() -> list[TextContent]:
        """查看网络连接状态"""
        r = _safe_run(["ss", "-tulnp"])
        return [TextContent(type="text", text=r.data.get("stdout", "") if r.success else (r.error or ""))]

    @server.tool()
    async def journalctl(service: str = "", lines: int = 50) -> list[TextContent]:
        """查看 systemd journal 日志"""
        cmd = ["journalctl", "-n", str(lines), "--no-pager"]
        if service:
            cmd.extend(["-u", service])
        r = _safe_run(cmd, timeout=15)
        return [TextContent(type="text", text=r.data.get("stdout", "") if r.success else (r.error or ""))]
