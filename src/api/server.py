"""Unix Domain Socket 服务器 — 接入层 + 直接执行。

架构:
  用户请求 → Unix Socket → api/server.py
    → intent/classifier.py (意图过滤)
      → [safe] → tool_dispatcher.py (直接执行工具)
      → [unsafe] → 拒绝
      → [needs-review] → 拒绝，建议人工审核
    → audit/logger.py (全量记录)
"""

from __future__ import annotations

import json
import os
import re
import socket
import uuid
from typing import Any

from ..audit.logger import AuditLogger
from ..intent.classifier import IntentClassifier
from ..contracts.types import SessionContext, ToolCallRecord

SOCKET_PATH = "/run/gcode/gcode.sock"

# 关键词 → 工具映射
_KEYWORD_TOOL_MAP = [
    (r"磁盘|空间|存储|df\b|disk", "df_h"),
    (r"cpu|处理器", "cpu_usage"),
    (r"内存|mem|ram", "mem_usage"),
    (r"io|磁盘读写|iostat", "io_stat"),
    (r"进程|ps\b|top\b|运行中", "ps_list"),
    (r"网络|端口|连接|netstat|ss\b", "netstat"),
    (r"系统信息|内核|版本|uname|主机名", "sys_info"),
    (r"日志|log|journalctl", "journalctl"),
    (r"服务.*状态|status.*service|nginx.*状态|systemctl\s+status", "service_status"),
    (r"重启.*服务|restart.*service|重启.*nginx|systemctl\s+restart", "service_restart"),
    (r"安装|装.*包|yum\s+install|dnf\s+install", "pkg_install"),
]


def _match_tool(query: str) -> tuple[str, dict]:
    """根据用户输入匹配工具和参数。"""
    for pattern, tool_name in _KEYWORD_TOOL_MAP:
        if re.search(pattern, query, re.IGNORECASE):
            params = {}
            # 提取服务名
            if tool_name in ("service_status", "service_restart"):
                m = re.search(r"(?:重启|查看|检查|status|restart)\s*(\S+)", query)
                if m:
                    params["name"] = m.group(1)
            # 提取日志行数
            if tool_name == "journalctl":
                m = re.search(r"(\d+)\s*条", query)
                if m:
                    params["lines"] = int(m.group(1))
            return tool_name, params
    # 默认返回系统信息
    return "sys_info", {}


class GcodeServer:
    """Gcode安全守卫服务器。"""

    def __init__(self, socket_path: str = SOCKET_PATH):
        self._socket_path = socket_path
        self._classifier = IntentClassifier()
        self._audit = AuditLogger()
        self._sock: socket.socket | None = None

    def start(self) -> None:
        """启动服务器。"""
        self._classifier.load()

        os.makedirs(os.path.dirname(self._socket_path), exist_ok=True)

        try:
            os.unlink(self._socket_path)
        except OSError:
            pass

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self._socket_path)
        os.chmod(self._socket_path, 0o660)
        self._sock.listen(5)

        print(f"Gcode Security Guard listening on {self._socket_path}")

        try:
            self._accept_loop()
        finally:
            self.shutdown()

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while True:
            conn, _ = self._sock.accept()
            try:
                self._handle(conn)
            except Exception as e:
                print(f"Handler error: {e}")
            finally:
                conn.close()

    def _handle(self, conn: socket.SocketType) -> None:
        """处理单条请求: 意图过滤 → 匹配工具 → 执行 → 审计记录。"""
        raw = conn.recv(65536)
        if not raw:
            return

        request = json.loads(raw)
        session_id = request.get("session_id", str(uuid.uuid4()))
        user_id = request.get("user_id", "unknown")
        query = request.get("query", "")

        # Step 1: 意图分类
        classification = self._classifier.classify(query)
        record = self._audit.create_record(
            user_id=user_id,
            session_id=session_id,
            original_query=query,
            intent_result=classification.intent,
            intent_confidence=classification.confidence,
            intent_categories=classification.categories,
        )
        self._audit.trace_event(record, f"Intent: {classification.intent} ({classification.top_label}, {classification.confidence:.2f})")

        with self._audit.trace(record):
            # Step 2: 安全决策
            if classification.intent == "unsafe":
                self._audit.finalize(
                    record, tools_called=[], request_ids=[],
                    results_summary="Rejected by intent filter",
                    final_status="rejected_by_intent", duration_total_ms=0,
                )
                self._send_json(conn, {
                    "status": "rejected",
                    "reason": "Intent classified as unsafe",
                    "detail": classification.top_label,
                })
                return

            if classification.intent == "needs-review":
                self._audit.finalize(
                    record, tools_called=[], request_ids=[],
                    results_summary="Needs human review",
                    final_status="rejected_by_intent", duration_total_ms=0,
                )
                self._send_json(conn, {
                    "status": "needs_review",
                    "reason": "Query requires human review",
                    "detail": classification.top_label,
                })
                return

            # Step 3: safe — 匹配工具并执行
            tool_name, params = _match_tool(query)
            self._audit.trace_event(record, f"Matched tool: {tool_name} params: {params}")

            from ..gcode.mcp.tool_dispatcher import dispatch, TOOL_RISK
            risk_level = TOOL_RISK.get(tool_name, "read_only")

            # 高风险工具需要 dry-run 确认
            if risk_level == "admin" and params.get("dry_run", True):
                params["dry_run"] = True

            result = dispatch(tool_name, params)

            tool_record = ToolCallRecord(
                audit_id=str(uuid.uuid4()),
                session_id=session_id,
                step_id=str(uuid.uuid4()),
                parent_step_id=None,
                tool_name=tool_name,
                params=params,
                risk_level=risk_level,
                timestamp=0,
            )

            self._audit.finalize(
                record,
                tools_called=[tool_name],
                request_ids=[tool_record.audit_id],
                results_summary=json.dumps(result, ensure_ascii=False)[:500],
                final_status="success" if result.get("success") else "execution_error",
                duration_total_ms=record.duration_total_ms,
            )

            self._send_json(conn, {
                "status": "success",
                "data": result,
                "audit_id": record.audit_id,
            })

    @staticmethod
    def _send_json(conn: socket.SocketType, data: dict) -> None:
        conn.sendall(json.dumps(data, ensure_ascii=False).encode() + b"\n")

    def shutdown(self) -> None:
        self._classifier.unload()
        if self._sock:
            self._sock.close()
        try:
            os.unlink(self._socket_path)
        except OSError:
            pass
        print("Gcode Security Guard stopped")


def main() -> None:
    server = GcodeServer()
    server.start()


if __name__ == "__main__":
    main()
