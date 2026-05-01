"""Alert deduplication — squash repeated alerts within a time window."""

from __future__ import annotations

from .models import get_db


class DedupEngine:
    """Lean dedup helper used by AlertRouter. Core dedup logic is in AlertEngine."""

    def should_suppress(self, rule_name: str, target: str, window_minutes: int = 5) -> bool:
        conn = get_db()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM alert_events WHERE rule_name = ? AND target = ? AND fired_at > datetime('now', ? || ' minutes')",
            (rule_name, target, f"-{window_minutes}"),
        ).fetchone()
        conn.close()
        return row["cnt"] > 0
