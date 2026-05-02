"""静态 Tool 注册表 — 12 个 MCP Tool 的 LLM 定义。"""
from __future__ import annotations

from .types import ToolDef

TOOL_DEFINITIONS: list[ToolDef] = [
    # === 只读感知 ===
    ToolDef(
        name="sys_info",
        description="获取系统基本信息：内核版本、主机名、架构、启动时间",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDef(
        name="ps_list",
        description="列出当前运行的进程信息",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDef(
        name="df_h",
        description="查看磁盘使用情况",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDef(
        name="netstat",
        description="查看网络连接状态",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDef(
        name="journalctl",
        description="查看 systemd journal 日志",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "服务名称，为空则查看全部"},
                "lines": {"type": "integer", "description": "显示行数，默认50"},
            },
            "required": [],
        },
    ),
    # === 指标采集 ===
    ToolDef(
        name="cpu_usage",
        description="获取 CPU 使用率（总体+每核）",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDef(
        name="mem_usage",
        description="获取内存使用情况",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDef(
        name="io_stat",
        description="获取磁盘 IO 统计",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDef(
        name="disk_health",
        description="检查指定路径的磁盘健康状态（使用率、inode）",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "磁盘路径，默认 /"},
            },
            "required": [],
        },
    ),
    # === 管理执行（高风险） ===
    ToolDef(
        name="service_status",
        description="查看指定 systemd 服务状态（中风险，无需确认）",
        parameters={
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "要查询的服务名称"},
            },
            "required": ["service_name"],
        },
    ),
    ToolDef(
        name="service_restart",
        description="重启指定 systemd 服务（高风险，需用户确认）",
        parameters={
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "要重启的服务名称"},
            },
            "required": ["service_name"],
        },
    ),
    ToolDef(
        name="pkg_install",
        description="安装 RPM 包（高风险，需用户确认）",
        parameters={
            "type": "object",
            "properties": {
                "package_name": {"type": "string", "description": "要安装的包名"},
            },
            "required": ["package_name"],
        },
    ),
]

READONLY_TOOL_NAMES = {
    "sys_info", "ps_list", "df_h", "netstat", "journalctl",
    "cpu_usage", "mem_usage", "io_stat", "disk_health", "service_status",
}

WRITE_TOOL_NAMES = {"service_restart", "pkg_install"}


def get_tools(allow_write: bool = False) -> list[ToolDef]:
    """返回 Tool 定义列表。allow_write=True 包含高风险写操作。"""
    if allow_write:
        return list(TOOL_DEFINITIONS)
    return [t for t in TOOL_DEFINITIONS if t.name in READONLY_TOOL_NAMES]
