"""Log pipeline data models with SQLite persistence."""

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
        CREATE TABLE IF NOT EXISTS log_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL,
            config TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS parse_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            source_filter TEXT NOT NULL DEFAULT '*',
            pattern TEXT NOT NULL,
            pattern_type TEXT NOT NULL DEFAULT 'regex',
            field_map TEXT DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS log_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            raw TEXT NOT NULL,
            parsed_fields TEXT DEFAULT '{}',
            level TEXT,
            message TEXT,
            ingested_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS anomaly_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detector_name TEXT NOT NULL,
            source TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            score REAL NOT NULL DEFAULT 0.0,
            match_count INTEGER NOT NULL DEFAULT 1,
            window_s INTEGER NOT NULL DEFAULT 60,
            details TEXT,
            detected_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS log_ingestion_state (
            source TEXT PRIMARY KEY,
            cursor_pos INTEGER NOT NULL DEFAULT 0,
            last_ingested_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_log_entries_source ON log_entries(source, ingested_at);
        CREATE INDEX IF NOT EXISTS idx_anomaly_findings_detected ON anomaly_findings(detected_at);
    """)
    conn.commit()
    conn.close()


@dataclass
class LogSourceModel:
    name: str
    source_type: str
    config: dict = field(default_factory=dict)
    enabled: bool = True
    id: int | None = None
    created_at: str = field(default_factory=_now)

    def save(self) -> None:
        conn = get_db()
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO log_sources (name, source_type, config, enabled, created_at) VALUES (?,?,?,?,?)",
                (self.name, self.source_type, json.dumps(self.config), int(self.enabled), self.created_at),
            )
            self.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE log_sources SET config=?, enabled=? WHERE id=?",
                (json.dumps(self.config), int(self.enabled), self.id),
            )
        conn.commit()
        conn.close()


@dataclass
class ParseRule:
    name: str
    pattern: str
    source_filter: str = "*"
    pattern_type: str = "regex"
    field_map: dict = field(default_factory=dict)
    enabled: bool = True
    id: int | None = None

    def save(self) -> None:
        conn = get_db()
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO parse_rules (name, source_filter, pattern, pattern_type, field_map, enabled) VALUES (?,?,?,?,?,?)",
                (self.name, self.source_filter, self.pattern, self.pattern_type, json.dumps(self.field_map), int(self.enabled)),
            )
            self.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE parse_rules SET source_filter=?, pattern=?, pattern_type=?, field_map=?, enabled=? WHERE id=?",
                (self.source_filter, self.pattern, self.pattern_type, json.dumps(self.field_map), int(self.enabled), self.id),
            )
        conn.commit()
        conn.close()


@dataclass
class LogEntry:
    source: str
    raw: str
    level: str | None = None
    message: str | None = None
    parsed_fields: dict = field(default_factory=dict)
    id: int | None = None
    ingested_at: str = field(default_factory=_now)

    def save(self) -> None:
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO log_entries (source, raw, parsed_fields, level, message, ingested_at) VALUES (?,?,?,?,?,?)",
            (self.source, self.raw, json.dumps(self.parsed_fields), self.level, self.message, self.ingested_at),
        )
        self.id = cur.lastrowid
        conn.commit()
        conn.close()


@dataclass
class AnomalyFinding:
    detector_name: str
    source: str
    message: str
    severity: str = "info"
    score: float = 0.0
    match_count: int = 1
    window_s: int = 60
    details: str | None = None
    id: int | None = None
    detected_at: str = field(default_factory=_now)

    def save(self) -> None:
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO anomaly_findings (detector_name, source, message, severity, score, match_count, window_s, details, detected_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (self.detector_name, self.source, self.message, self.severity, self.score, self.match_count, self.window_s, self.details, self.detected_at),
        )
        self.id = cur.lastrowid
        conn.commit()
        conn.close()
