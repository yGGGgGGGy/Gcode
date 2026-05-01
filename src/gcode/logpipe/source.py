from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Iterator

from .models import LogEntry, init_db


class LogSource:
    def __init__(self, source_name: str = "", file_path: str | None = None) -> None:
        self.source_name = source_name
        self.file_path = file_path
        init_db()

    def tail(self, follow: bool = False) -> Iterator[LogEntry]:
        if self.file_path:
            path = Path(self.file_path)
        else:
            path = self._resolve_path()

        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {path}")

        with open(path) as fh:
            # Seek to end for follow mode
            if follow:
                fh.seek(0, 2)
            for line in self._read_lines(fh, follow):
                entry = LogEntry(
                    source=self.source_name or str(path),
                    raw=line.rstrip("\n"),
                    timestamp="",
                )
                entry.save()
                yield entry

    def _read_lines(self, fh, follow: bool) -> Iterator[str]:
        while True:
            line = fh.readline()
            if line:
                yield line
            elif follow:
                time.sleep(0.25)
            else:
                break

    def _resolve_path(self) -> Path:
        from .models import get_db
        conn = get_db()
        row = conn.execute("SELECT config FROM log_sources WHERE name = ? AND enabled = 1", (self.source_name,)).fetchone()
        conn.close()
        if row is None:
            raise ValueError(f"No enabled log source named '{self.source_name}'")
        import json
        config = json.loads(row["config"])
        return Path(config.get("path", ""))
