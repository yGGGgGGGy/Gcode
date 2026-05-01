"""管理执行工具 — 风险等级 MEDIUM/HIGH
执行系统管理操作，需要通过权限门禁和确认流程。"""
from mcp.server import Server
from mcp.types import Tool, TextContent

from .executor import execute_command, ExecutionRequest
from ....contracts.types import RiskLevel

RISK = "admin"


def register_management_tools(server: Server):
    @server.tool()
    async def service_restart(service_name: str) -> list[TextContent]:
        """重启指定 systemd 服务（需确认）"""
        safe_name = service_name.replace("/", "").replace(";", "").replace("&", "")
        if safe_name != service_name:
            return [TextContent(type="text", text=f"[BLOCKED] 服务名包含非法字符: {service_name}")]

        req = ExecutionRequest(
            cmd=["systemctl", "restart", safe_name],
            risk_level="admin",
            needs_confirmation=True,
            dry_run_cmd=["systemctl", "status", safe_name],
        )
        result = execute_command(req)
        return [TextContent(type="text", text=str(result.data))]

    @server.tool()
    async def pkg_install(package_name: str) -> list[TextContent]:
        """安装 RPM 包（麒麟系统，需确认）"""
        safe_name = package_name.replace("/", "").replace(";", "").replace("&", "")
        if safe_name != package_name:
            return [TextContent(type="text", text=f"[BLOCKED] 包名包含非法字符: {package_name}")]

        req = ExecutionRequest(
            cmd=["dnf", "install", "-y", safe_name],
            risk_level="admin",
            needs_confirmation=True,
            dry_run_cmd=["dnf", "list", safe_name],
        )
        result = execute_command(req)
        return [TextContent(type="text", text=str(result.data))]

    @server.tool()
    async def service_status(service_name: str) -> list[TextContent]:
        """查看服务状态（中风险，无需确认）"""
        safe_name = service_name.replace("/", "").replace(";", "").replace("&", "")
        if safe_name != service_name:
            return [TextContent(type="text", text=f"[BLOCKED] 服务名包含非法字符: {service_name}")]

        req = ExecutionRequest(
            cmd=["systemctl", "status", safe_name, "--no-pager"],
            risk_level="read_write",
            needs_confirmation=False,
        )
        result = execute_command(req)
        return [TextContent(type="text", text=str(result.data))]
