from __future__ import annotations

from .models import AlertRule, AlertEvent, get_db, init_db
from .channels import ChannelRegistry


class AlertEngine:
    def __init__(self) -> None:
        init_db()

    def evaluate(self, target: str, metrics: dict[str, float]) -> list[AlertEvent]:
        conn = get_db()
        rules = [
            AlertRule(
                id=r["id"], name=r["name"], metric=r["metric"],
                threshold_gt=r["threshold_gt"], threshold_lt=r["threshold_lt"],
                enabled=bool(r["enabled"]), created_at=r["created_at"],
            )
            for r in conn.execute("SELECT * FROM alert_rules WHERE enabled = 1").fetchall()
        ]
        conn.close()

        events: list[AlertEvent] = []
        for rule in rules:
            value = metrics.get(rule.metric)
            if value is None:
                continue

            fired = False
            if rule.threshold_gt is not None and value > rule.threshold_gt:
                fired = True
            if rule.threshold_lt is not None and value < rule.threshold_lt:
                fired = True

            if fired:
                if self._is_suppressed(rule.name, target):
                    continue
                if self._is_duplicate(rule.name, target):
                    continue
                event = AlertEvent(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    target=target,
                    message=f"{rule.metric}={value} (threshold: gt={rule.threshold_gt}, lt={rule.threshold_lt})",
                    severity=self._severity(rule, value),
                    notify_channels=self._resolve_channels(rule.name),
                )
                event.save()
                events.append(event)

        return events

    def _severity(self, rule: AlertRule, value: float) -> str:
        if rule.threshold_gt and value > rule.threshold_gt * 1.5:
            return "critical"
        if rule.threshold_lt and value < rule.threshold_lt * 0.5:
            return "critical"
        return "warning"

    def _is_duplicate(self, rule_name: str, target: str) -> bool:
        """Suppress if the same rule+target fired in the last 5 minutes."""
        conn = get_db()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM alert_events WHERE rule_name = ? AND target = ? AND fired_at > datetime('now', '-5 minutes')",
            (rule_name, target),
        ).fetchone()
        conn.close()
        return row["cnt"] > 0

    def _is_suppressed(self, rule_name: str, target: str) -> bool:
        conn = get_db()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM alert_suppressions WHERE rule_name = ? AND target = ? AND until > datetime('now')",
            (rule_name, target),
        ).fetchone()
        conn.close()
        return row["cnt"] > 0

    def _resolve_channels(self, rule_name: str) -> list[str]:
        registry = ChannelRegistry()
        return [n for n, _ in registry.list_all()]

    def suppress(self, rule_name: str, target: str, duration_m: int = 30) -> None:
        conn = get_db()
        conn.execute(
            "INSERT INTO alert_suppressions (rule_name, target, until) VALUES (?, ?, datetime('now', ? || ' minutes'))",
            (rule_name, target, str(duration_m)),
        )
        conn.commit()
        conn.close()
