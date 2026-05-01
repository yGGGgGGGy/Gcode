"""指标采集工具 — 风险等级 LOW
采集 CPU、内存、IO、磁盘健康等运维指标。"""
from mcp.server import Server
from mcp.types import Tool, TextContent
import json

RISK = "low"


def register_metrics_tools(server: Server):
    @server.tool()
    async def cpu_usage() -> list[TextContent]:
        """获取 CPU 使用率（总体+每核）"""
        import psutil
        data = {
            "percent": psutil.cpu_percent(interval=1),
            "per_cpu": psutil.cpu_percent(interval=1, percpu=True),
            "count": psutil.cpu_count(),
        }
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    @server.tool()
    async def mem_usage() -> list[TextContent]:
        """获取内存使用情况"""
        import psutil
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        data = {
            "memory": {"total_gb": round(mem.total / (1024**3), 1), "used_gb": round(mem.used / (1024**3), 1),
                       "percent": mem.percent, "available_gb": round(mem.available / (1024**3), 1)},
            "swap": {"total_gb": round(swap.total / (1024**3), 1), "used_gb": round(swap.used / (1024**3), 1),
                     "percent": swap.percent},
        }
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    @server.tool()
    async def io_stat() -> list[TextContent]:
        """获取磁盘 IO 统计"""
        import psutil
        io = psutil.disk_io_counters()
        data = {
            "read_count": io.read_count,
            "write_count": io.write_count,
            "read_mb": round(io.read_bytes / (1024**2), 1),
            "write_mb": round(io.write_bytes / (1024**2), 1),
        }
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    @server.tool()
    async def disk_health(path: str = "/") -> list[TextContent]:
        """检查指定路径的磁盘健康状态（使用率、inode）"""
        import psutil
        usage = psutil.disk_usage(path)
        data = {
            "path": path,
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "percent": usage.percent,
            "warning": usage.percent > 85,
        }
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]
