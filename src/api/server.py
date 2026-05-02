"""Unix Domain Socket 服务器 — 接入层 + 推理 + 执行。

架构:
  用户请求 → Unix Socket → api/server.py
    → intent/classifier.py (意图过滤)
      → [safe] → LLM 推理（DeepSeek/Qwen）→ 工具执行
      → [unsafe] → 拒绝
      → [needs-review] → 拒绝，建议人工审核
    → audit/logger.py (全量记录)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import uuid
from typing import Any

from ..audit.logger import AuditLogger
from ..intent.classifier import IntentClassifier
from ..contracts.types import SessionContext, ToolCallRecord
from ..gcode.mcp.tool_dispatcher import dispatch, TOOL_RISK

SOCKET_PATH = "/run/gcode/gcode.sock"


def _create_reasoner():
    """根据环境变量创建推理器（延迟加载）。"""
    provider_name = os.environ.get("GCODE_LLM_PROVIDER", "").lower()

    if provider_name == "deepseek":
        from ..gcode.reasoning.providers.openai_compat import create_deepseek_provider
        api_key = os.environ.get("GCODE_DEEPSEEK_API_KEY", "")
        model = os.environ.get("GCODE_DEEPSEEK_MODEL", "deepseek-chat")
        if not api_key:
            return None
        provider = create_deepseek_provider(api_key=api_key, model=model)
    elif provider_name == "qwen":
        from ..gcode.reasoning.providers.openai_compat import create_qwen_provider
        api_key = os.environ.get("GCODE_QWEN_API_KEY", "")
        model = os.environ.get("GCODE_QWEN_MODEL", "qwen-plus")
        if not api_key:
            return None
        provider = create_qwen_provider(api_key=api_key, model=model)
    elif provider_name == "claude":
        from ..gcode.reasoning.providers.anthropic import create_claude_provider
        api_key = os.environ.get("GCODE_CLAUDE_API_KEY", "")
        model = os.environ.get("GCODE_CLAUDE_MODEL", "claude-sonnet-4-20250514")
        if not api_key:
            return None
        provider = create_claude_provider(api_key=api_key, model=model)
    elif provider_name == "ollama":
        from ..gcode.reasoning.providers.openai_compat import create_ollama_provider
        url = os.environ.get("GCODE_OLLAMA_URL", "http://localhost:11434")
        model = os.environ.get("GCODE_OLLAMA_MODEL", "qwen2.5:7b")
        provider = create_ollama_provider(model=model, base_url=f"{url}/v1")
    else:
        return None

    from ..gcode.reasoning.reasoner import Reasoner
    return Reasoner(provider=provider)


def _reason_with_llm(reasoner, query: str) -> dict:
    """调用 LLM 推理并执行工具，返回结果。"""
    try:
        response = asyncio.run(reasoner.reason(query, allow_write=False))
        # 如果 LLM 返回了文本（已包含工具结果），直接返回
        if response.text:
            return {"success": True, "stdout": response.text, "stderr": "", "rc": 0}
        # 如果有工具结果，汇总返回
        if response.tool_results:
            parts = []
            for tr in response.tool_results:
                parts.append(f"[{tr['tool']}]\n{tr['result']}")
            return {"success": True, "stdout": "\n\n".join(parts), "stderr": "", "rc": 0}
        return {"success": True, "stdout": response.text or "（无结果）", "stderr": "", "rc": 0}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": f"LLM 推理失败: {e}", "rc": -1}


# 关键词 → 工具映射（LLM 不可用时的降级方案）
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
        self._reasoner = _create_reasoner()
        if self._reasoner:
            print(f"  LLM 推理已启用: {self._reasoner._provider.name}")
        else:
            print("  LLM 未配置，使用关键词匹配降级方案")

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
                try:
                    self._send_json(conn, {"status": "error", "error": str(e)})
                except Exception:
                    pass
            finally:
                conn.close()

    def _handle(self, conn: socket.SocketType) -> None:
        """处理单条请求: 意图过滤 → 匹配工具 → 执行 → 审计记录。"""
        raw = conn.recv(65536)
        if not raw:
            return

        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(conn, {"status": "error", "error": "无效的 JSON 请求"})
            return
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

            # Step 3: safe — 推理 + 执行
            if self._reasoner:
                # 使用 LLM 推理决策
                self._audit.trace_event(record, "Using LLM reasoning")
                result = _reason_with_llm(self._reasoner, query)
                tool_name = "llm_reasoning"
                params = {"query": query}
            else:
                # 降级：关键词匹配
                tool_name, params = _match_tool(query)
                self._audit.trace_event(record, f"Matched tool: {tool_name} params: {params}")
                risk_level = TOOL_RISK.get(tool_name, "read_only")
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
                risk_level=TOOL_RISK.get(tool_name, "read_only"),
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
