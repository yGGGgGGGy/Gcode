from __future__ import annotations

import socket
import time
from urllib.request import Request, urlopen

from .models import HealthCheckResult, init_db


class HealthChecker:
    def __init__(self, timeout: int = 5) -> None:
        self.timeout = timeout
        init_db()

    def run(self, target: str, check_type: str) -> HealthCheckResult:
        if check_type == "http":
            return self._check_http(target)
        elif check_type == "tcp":
            return self._check_tcp(target)
        elif check_type == "process":
            return self._check_process(target)
        else:
            raise ValueError(f"Unknown check type: {check_type}")

    def _check_http(self, target: str) -> HealthCheckResult:
        start = time.monotonic()
        try:
            req = Request(target, method="HEAD")
            resp = urlopen(req, timeout=self.timeout)
            healthy = 200 <= resp.status < 400
            latency = (time.monotonic() - start) * 1000
            result = HealthCheckResult(target=target, check_type="http", healthy=healthy, latency_ms=round(latency, 2))
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            result = HealthCheckResult(target=target, check_type="http", healthy=False, latency_ms=round(latency, 2), error=str(e))
        result.save()
        return result

    def _check_tcp(self, target: str) -> HealthCheckResult:
        host, _, port_str = target.partition(":")
        port = int(port_str) if port_str else 80

        start = time.monotonic()
        try:
            sock = socket.create_connection((host, port), timeout=self.timeout)
            sock.close()
            latency = (time.monotonic() - start) * 1000
            result = HealthCheckResult(target=target, check_type="tcp", healthy=True, latency_ms=round(latency, 2))
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            result = HealthCheckResult(target=target, check_type="tcp", healthy=False, latency_ms=round(latency, 2), error=str(e))
        result.save()
        return result

    def _check_process(self, target: str) -> HealthCheckResult:
        import subprocess

        start = time.monotonic()
        try:
            subprocess.run(["pidof", target], check=True, capture_output=True, timeout=self.timeout)
            latency = (time.monotonic() - start) * 1000
            result = HealthCheckResult(target=target, check_type="process", healthy=True, latency_ms=round(latency, 2))
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            result = HealthCheckResult(target=target, check_type="process", healthy=False, latency_ms=round(latency, 2), error=str(e))
        result.save()
        return result
