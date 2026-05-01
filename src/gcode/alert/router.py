from __future__ import annotations

from dataclasses import dataclass, field
from .models import AlertEvent


@dataclass
class RouteRule:
    name: str
    condition_field: str  # severity, rule_name, target
    condition_value: str
    channels: list[str] = field(default_factory=list)
    priority: int = 0


class AlertRouter:
    def __init__(self, rules: list[RouteRule] | None = None) -> None:
        self.rules = rules or []

    def route(self, event: AlertEvent) -> list[str]:
        channels: list[str] = []
        remaining = sorted(self.rules, key=lambda r: -r.priority)

        for rule in remaining:
            if self._match(event, rule):
                channels.extend(rule.channels)

        # Dedup preserving order
        seen: set[str] = set()
        result: list[str] = []
        for ch in channels:
            if ch not in seen:
                seen.add(ch)
                result.append(ch)
        return result

    def _match(self, event: AlertEvent, rule: RouteRule) -> bool:
        field_value = getattr(event, rule.condition_field, None)
        if field_value is None:
            return False
        return str(field_value).lower() == rule.condition_value.lower()
