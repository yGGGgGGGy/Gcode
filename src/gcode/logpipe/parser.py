"""Log parser chain — regex, JSON, and timestamp extraction."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .models import LogEntry, ParseRule, get_db


class ParserChain:
    """Ordered chain of parse rules applied to each log entry."""

    def __init__(self) -> None:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM log_parse_rules WHERE enabled = 1 ORDER BY id"
        ).fetchall()
        conn.close()
        self.rules: list[ParseRule] = [
            ParseRule(
                id=r["id"],
                name=r["name"],
                source_filter=r["source_filter"],
                pattern=r["pattern"],
                pattern_type=r["pattern_type"],
                field_map=json.loads(r["field_map"]),
                enabled=bool(r["enabled"]),
            )
            for r in rows
        ]

    def apply(self, entry: LogEntry) -> LogEntry:
        for rule in self.rules:
            if not self._source_matches(entry.source, rule.source_filter):
                continue
            if rule.pattern_type == "regex":
                entry = self._apply_regex(entry, rule)
            elif rule.pattern_type == "json":
                entry = self._apply_json(entry)
            elif rule.pattern_type == "syslog":
                entry = self._apply_syslog(entry)
        return entry

    def _source_matches(self, source: str, source_filter: str) -> bool:
        if source_filter == "*":
            return True
        if source_filter.startswith("glob:"):
            import fnmatch

            return fnmatch.fnmatch(source, source_filter[5:])
        return source_filter in source

    def _apply_regex(self, entry: LogEntry, rule: ParseRule) -> LogEntry:
        m = re.search(rule.pattern, entry.raw)
        if m:
            fields = m.groupdict() or {str(i): v for i, v in enumerate(m.groups())}
            for src_key, dst_key in rule.field_map.items():
                if src_key in fields:
                    entry.parsed_fields[dst_key] = fields[src_key]
            if "level" in entry.parsed_fields:
                entry.level = entry.parsed_fields["level"]
            if "message" in entry.parsed_fields:
                entry.message = entry.parsed_fields["message"]
        return entry

    def _apply_json(self, entry: LogEntry) -> LogEntry:
        try:
            obj = json.loads(entry.raw)
            if isinstance(obj, dict):
                entry.parsed_fields.update(obj)
                entry.level = obj.get("level") or obj.get("severity")
                entry.message = obj.get("message") or obj.get("msg")
        except json.JSONDecodeError:
            pass
        return entry

    def _apply_syslog(self, entry: LogEntry) -> LogEntry:
        # RFC 3164: <pri>timestamp hostname message
        m = re.match(r"^<(\d+)>(\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)", entry.raw)
        if m:
            entry.parsed_fields["syslog_pri"] = m.group(1)
            entry.parsed_fields["syslog_ts"] = m.group(2)
            entry.parsed_fields["syslog_host"] = m.group(3)
            message = m.group(4)
            # Try to extract structured content from message
            level_keywords = {"ERROR": "error", "WARN": "warn", "INFO": "info", "DEBUG": "debug", "CRIT": "critical"}
            for kw, lvl in level_keywords.items():
                if message.startswith(kw) or kw in message.upper():
                    entry.level = lvl
                    break
            entry.message = message
        return entry
