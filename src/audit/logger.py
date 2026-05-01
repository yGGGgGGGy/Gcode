"""审计日志记录器 — 全链路思维链审计。"""

from __future__ import annotations

import time
import traceback
from contextlib import contextmanager
from typing import Any

from .models import AuditRecord, AuditStatus, AuditStore


class AuditLogger:
    """审计日志记录器，所有查询全量写入SQLite。"""

    def __init__(self, store: AuditStore | None = None):
        self._store = store or AuditStore()
        self._store.init_db()

    def create_record(
        self,
        user_id: str,
        session_id: str,
        original_query: str,
        intent_result: str,
        intent_confidence: float,
        intent_categories: list[str],
        chain_of_thought: str = "",
    ) -> AuditRecord:
        return AuditRecord(
            user_id=user_id,
            session_id=session_id,
            original_query=original_query,
            intent_result=intent_result,
            intent_confidence=intent_confidence,
            intent_categories=intent_categories,
            chain_of_thought=chain_of_thought,
        )

    def finalize(
        self,
        record: AuditRecord,
        tools_called: list[str],
        request_ids: list[str],
        results_summary: str,
        final_status: AuditStatus,
        duration_total_ms: int,
    ) -> None:
        record.tools_called = tools_called
        record.request_ids = request_ids
        record.results_summary = results_summary
        record.final_status = final_status
        record.duration_total_ms = duration_total_ms
        self._store.insert(record)

    @contextmanager
    def trace(self, record: AuditRecord):
        """上下文管理器，追踪执行全过程，自动计算耗时。"""
        t0 = time.monotonic()
        events: list[str] = []
        try:
            yield events
        except Exception:
            record.final_status = "execution_error"
            record.chain_of_thought += "\n".join(events)
            record.chain_of_thought += f"\nERROR: {traceback.format_exc()}"
            raise
        finally:
            elapsed = int((time.monotonic() - t0) * 1000)
            record.duration_total_ms = elapsed

    def trace_event(self, record: AuditRecord, event: str) -> None:
        record.chain_of_thought += f"[{int(time.monotonic() * 1000)}] {event}\n"

    def query_history(self, session_id: str) -> list[dict[str, Any]]:
        return self._store.query_by_session(session_id)

    def user_history(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return self._store.query_by_user(user_id, limit)
