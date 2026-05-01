from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "gcode.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            metric TEXT NOT NULL,
            threshold_gt REAL,
            threshold_lt REAL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alert_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            rule_name TEXT NOT NULL,
            target TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'warning',
            fired_at TEXT NOT NULL,
            acked INTEGER NOT NULL DEFAULT 0,
            notify_channels TEXT DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS alert_suppressions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_name TEXT NOT NULL,
            target TEXT NOT NULL,
            until TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notification_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            config_json TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1
        );
    """)
    conn.commit()
    conn.close()


@dataclass
class AlertRule:
    name: str
    metric: str
    threshold_gt: float | None = None
    threshold_lt: float | None = None
    enabled: bool = True
    id: int | None = None
    created_at: str = field(default_factory=_now)

    def save(self) -> None:
        conn = get_db()
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO alert_rules (name, metric, threshold_gt, threshold_lt, enabled, created_at) VALUES (?,?,?,?,?,?)",
                (self.name, self.metric, self.threshold_gt, self.threshold_lt, int(self.enabled), self.created_at),
            )
            self.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE alert_rules SET name=?, metric=?, threshold_gt=?, threshold_lt=?, enabled=? WHERE id=?",
                (self.name, self.metric, self.threshold_gt, self.threshold_lt, int(self.enabled), self.id),
            )
        conn.commit()
        conn.close()


@dataclass
class AlertEvent:
    rule_name: str
    target: str
    message: str
    severity: str = "warning"
    rule_id: int | None = None
    id: int | None = None
    fired_at: str = field(default_factory=_now)
    acked: bool = False
    notify_channels: list[str] = field(default_factory=list)

    def save(self) -> None:
        conn = get_db()
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO alert_events (rule_id, rule_name, target, message, severity, fired_at, acked, notify_channels) VALUES (?,?,?,?,?,?,?,?)",
                (self.rule_id, self.rule_name, self.target, self.message, self.severity, self.fired_at, int(self.acked), json.dumps(self.notify_channels)),
            )
            self.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE alert_events SET acked=? WHERE id=?",
                (int(self.acked), self.id),
            )
        conn.commit()
        conn.close()
