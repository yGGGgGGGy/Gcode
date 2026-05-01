from __future__ import annotations

import os
import platform

from .models import MetricReading, init_db


class Collector:
    def __init__(self, metrics: list[str] | None = None) -> None:
        self.metrics = metrics or ["cpu", "mem"]
        init_db()

    def collect(self, target: str) -> dict[str, float]:
        results: dict[str, float] = {}

        if target == "localhost" or target in ("127.0.0.1", "::1") or target == platform.node():
            if "cpu" in self.metrics:
                results["cpu"] = self._cpu_percent()
            if "mem" in self.metrics:
                results["mem"] = self._mem_percent()
            if "disk" in self.metrics:
                results["disk"] = self._disk_percent()
            if "load" in self.metrics:
                results["load"] = self._load_avg()
        else:
            # Remote target — placeholder for agent-based collection
            results["cpu"] = -1.0
            results["mem"] = -1.0
            results["disk"] = -1.0

        for metric, value in results.items():
            MetricReading(target=target, metric=metric, value=value).save()

        return results

    def _cpu_percent(self) -> float:
        try:
            import psutil
            return psutil.cpu_percent(interval=0.5)
        except ImportError:
            return -1.0

    def _mem_percent(self) -> float:
        try:
            import psutil
            return psutil.virtual_memory().percent
        except ImportError:
            return -1.0

    def _disk_percent(self) -> float:
        try:
            import psutil
            return psutil.disk_usage("/").percent
        except ImportError:
            return -1.0

    def _load_avg(self) -> float:
        try:
            return os.getloadavg()[0]
        except OSError:
            return -1.0
