from __future__ import annotations

from .collector import Collector
from .models import ThresholdBreach, init_db


class ThresholdEngine:
    def __init__(self, thresholds: dict[str, float]) -> None:
        self.thresholds = thresholds
        self.collector = Collector(metrics=list(thresholds.keys()))
        init_db()

    def evaluate(self, target: str) -> list[ThresholdBreach]:
        readings = self.collector.collect(target)
        breaches: list[ThresholdBreach] = []
        for metric, threshold in self.thresholds.items():
            value = readings.get(metric, -1.0)
            if value > threshold:
                breach = ThresholdBreach(target=target, metric=metric, value=value, threshold=threshold)
                breach.save()
                breaches.append(breach)
        return breaches
