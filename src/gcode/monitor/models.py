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
        CREATE TABLE IF NOT EXISTS health_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            check_type TEXT NOT NULL,
            healthy INTEGER NOT NULL,
            latency_ms REAL,
            error TEXT,
            checked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            collected_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS threshold_breaches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            threshold REAL NOT NULL,
            breached_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


@dataclass
class HealthCheckResult:
    target: str
    check_type: str
    healthy: bool
    latency_ms: float
    error: str | None = None
    checked_at: str = field(default_factory=_now)

    def save(self) -> None:
        conn = get_db()
        conn.execute(
            "INSERT INTO health_checks (target, check_type, healthy, latency_ms, error, checked_at) VALUES (?,?,?,?,?,?)",
            (self.target, self.check_type, int(self.healthy), self.latency_ms, self.error, self.checked_at),
        )
        conn.commit()
        conn.close()


@dataclass
class MetricReading:
    target: str
    metric: str
    value: float
    collected_at: str = field(default_factory=_now)

    def save(self) -> None:
        conn = get_db()
        conn.execute(
            "INSERT INTO metrics (target, metric, value, collected_at) VALUES (?,?,?,?)",
            (self.target, self.metric, self.value, self.collected_at),
        )
        conn.commit()
        conn.close()


@dataclass
class ThresholdBreach:
    target: str
    metric: str
    value: float
    threshold: float
    breached_at: str = field(default_factory=_now)

    def save(self) -> None:
        conn = get_db()
        conn.execute(
            "INSERT INTO threshold_breaches (target, metric, value, threshold, breached_at) VALUES (?,?,?,?,?)",
            (self.target, self.metric, self.value, self.threshold, self.breached_at),
        )
        conn.commit()
        conn.close()
