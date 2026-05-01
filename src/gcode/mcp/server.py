"""MCP Server 入口 — FastMCP 协议实现"""
import uuid
import time
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server

from ....contracts.types import SessionContext, ToolCallRecord, ToolResult, RiskLevel
from .tools_readonly import register_readonly_tools
from .tools_metrics import register_metrics_tools
from .tools_management import register_management_tools

logger = logging.getLogger("gcode.mcp_server")


class GcodeMCPServer:
    """Gcode 智能运维 MCP Server"""

    def __init__(self):
        self.server = Server("gcode-mcp-server")
        self._register_tools()
        self._active_sessions: dict[str, SessionContext] = {}

    def _register_tools(self):
        register_readonly_tools(self.server)
        register_metrics_tools(self.server)
        register_management_tools(self.server)

    def set_session_context(self, ctx: SessionContext):
        """接收来自意图过滤层的 SessionContext"""
        self._active_sessions[ctx.session_id] = ctx
        logger.info("session=%s risk=%s score=%.2f", ctx.session_id, ctx.risk_verdict, ctx.risk_score)

    def create_tool_record(
        self,
        session_id: str,
        step_id: str,
        tool_name: str,
        params: dict,
        parent_step_id: str | None = None,
        risk_level: RiskLevel = "read_only",
    ) -> ToolCallRecord:
        return ToolCallRecord(
            audit_id=str(uuid.uuid4()),
            session_id=session_id,
            step_id=step_id,
            parent_step_id=parent_step_id,
            tool_name=tool_name,
            params=params,
            risk_level=risk_level,
            timestamp=time.time(),
        )

    async def run(self):
        async with stdio_server() as (reader, writer):
            await self.server.run(reader, writer)


server = GcodeMCPServer()
