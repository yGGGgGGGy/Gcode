"""Log source adapters — file tail, journald, stdin."""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path

from .models import LogEntry, get_db, init_db


class FileTailSource:
    """Tail a log file, tracking cursor position in SQLite for resume."""

    def __init__(self, path: str | Path, label: str | None = None) -> None:
        self.path = Path(path)
        self.label = label or str(self.path)
        init_db()

    def _read_cursor(self) -> int:
        conn = get_db()
        row = conn.execute(
            "SELECT cursor_pos FROM log_ingestion_state WHERE source = ?", (self.label,)
        ).fetchone()
        conn.close()
        return row["cursor_pos"] if row else 0

    def _write_cursor(self, pos: int) -> None:
        from datetime import datetime, timezone

        conn = get_db()
        conn.execute(
            "INSERT INTO log_ingestion_state (source, cursor_pos, last_ingested_at) VALUES (?,?,?) ON CONFLICT(source) DO UPDATE SET cursor_pos=excluded.cursor_pos, last_ingested_at=excluded.last_ingested_at",
            (self.label, pos, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    def tail(self) -> Generator[LogEntry, None, None]:
        if not self.path.exists():
            return

        file_size = self.path.stat().st_size
        cursor = self._read_cursor()

        if cursor > file_size:
            cursor = 0  # file was truncated

        with open(self.path, encoding="utf-8", errors="replace") as f:
            f.seek(cursor)
            for line in f:
                stripped = line.rstrip("\n\r")
                if stripped:
                    yield LogEntry(source=self.label, raw=stripped)
            self._write_cursor(f.tell())


class StdinSource:
    """Read log lines from stdin (piped input)."""

    def __init__(self, label: str = "stdin") -> None:
        self.label = label

    def read(self) -> Generator[LogEntry, None, None]:
        for line in sys.stdin:
            stripped = line.rstrip("\n\r")
            if stripped:
                yield LogEntry(source=self.label, raw=stripped)


class JournaldSource:
    """Query systemd journal via journalctl."""

    def __init__(self, unit: str | None = None, label: str | None = None) -> None:
        self.unit = unit
        self.label = label or f"journald:{unit or 'all'}"

    def query(self, lines: int = 100) -> Generator[LogEntry, None, None]:
        try:
            import subprocess

            cmd = ["journalctl", "--no-pager", "-n", str(lines), "-o", "short-iso"]
            if self.unit:
                cmd.extend(["-u", self.unit])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            for line in result.stdout.strip().split("\n"):
                stripped = line.rstrip()
                if stripped:
                    yield LogEntry(source=self.label, raw=stripped)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return
