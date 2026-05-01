from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .models import LogEntry, ParseRule, get_db, init_db


class ParsePipeline:
    def __init__(self) -> None:
        init_db()
        self._rules: list[ParseRule] | None = None

    def _load_rules(self) -> list[ParseRule]:
        if self._rules is not None:
            return self._rules
        conn = get_db()
        rows = conn.execute("SELECT * FROM parse_rules WHERE enabled = 1 ORDER BY id").fetchall()
        conn.close()
        self._rules = [
            ParseRule(
                id=r["id"], name=r["name"], pattern=r["pattern"],
                source=r["source"], enabled=bool(r["enabled"]), created_at=r["created_at"],
            )
            for r in rows
        ]
        return self._rules

    def process(self, entry: LogEntry, source: str | None = None) -> LogEntry:
        """Run entry through all applicable parse rules. First match wins for field extraction."""
        rules = self._load_rules()

        entry.timestamp = entry.timestamp or datetime.now(timezone.utc).isoformat()

        for rule in rules:
            if rule.source and source and rule.source != source:
                continue
            try:
                match = re.search(rule.pattern, entry.raw)
                if match:
                    groups = match.groupdict()
                    if "level" in groups:
                        entry.level = groups["level"]
                    if "message" in groups:
                        entry.message = groups["message"]
                    if "timestamp" in groups:
                        entry.timestamp = groups["timestamp"]
                    entry.parsed_json = json.dumps(groups)
                    break
            except re.error:
                continue

        if not entry.message:
            entry.message = entry.raw

        return entry

    def reload(self) -> None:
        self._rules = None
