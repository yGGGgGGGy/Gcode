"""SQLite审计数据模型。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

AuditStatus = Literal[
    "success",
    "rejected_by_intent",
    "rejected_by_executor",
    "execution_error",
]


@dataclass
class AuditRecord:
    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    user_id: str = ""
    session_id: str = ""
    original_query: str = ""
    intent_result: str = ""
    intent_confidence: float = 0.0
    intent_categories: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    request_ids: list[str] = field(default_factory=list)
    results_summary: str = ""
    final_status: AuditStatus = "success"
    chain_of_thought: str = ""
    duration_total_ms: int = 0


class AuditStore:
    """SQLite审计日志存储。"""

    def __init__(self, db_path: str = "gcode_audit.db"):
        self._db_path = db_path

    def init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_records (
                    audit_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    original_query TEXT NOT NULL,
                    intent_result TEXT NOT NULL,
                    intent_confidence REAL NOT NULL,
                    intent_categories TEXT NOT NULL,
                    tools_called TEXT NOT NULL,
                    request_ids TEXT NOT NULL,
                    results_summary TEXT NOT NULL,
                    final_status TEXT NOT NULL,
                    chain_of_thought TEXT NOT NULL,
                    duration_total_ms INTEGER NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_records(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_records(user_id)"
            )
            conn.commit()

    def insert(self, record: AuditRecord) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.audit_id,
                    record.timestamp,
                    record.user_id,
                    record.session_id,
                    record.original_query,
                    record.intent_result,
                    record.intent_confidence,
                    json.dumps(record.intent_categories),
                    json.dumps(record.tools_called),
                    json.dumps(record.request_ids),
                    record.results_summary,
                    record.final_status,
                    record.chain_of_thought,
                    record.duration_total_ms,
                ),
            )
            conn.commit()

    def query_by_session(self, session_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit_records WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def query_by_user(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit_records WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
