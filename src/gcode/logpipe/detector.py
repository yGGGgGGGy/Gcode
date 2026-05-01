"""Log anomaly detection — keyword spikes, error rate, pattern matching."""

from __future__ import annotations

import re
from collections import deque
from datetime import datetime, timezone

from .models import AnomalyFinding, LogEntry, get_db, init_db


# Built-in patterns aligned with m1's DEFAULT_PATTERNS idea
DEFAULT_PATTERNS = [
    (r"(?i)(error|exception|fatal|critical|panic)", "error", 0.8),
    (r"(?i)(timeout|timed.?out|deadline.?exceeded)", "timeout", 0.7),
    (r"(?i)(connection.?refused|connection.?reset|broken.?pipe)", "connection", 0.7),
    (r"(?i)(out.?of.?memory|oom|memory.?leak)", "resource", 0.9),
    (r"(?i)(permission.?denied|access.?denied|unauthorized|forbidden)", "security", 0.85),
    (r"(?i)(rate.?limit|throttl|too.?many.?request)", "ratelimit", 0.6),
]


class AnomalyDetector:
    """Pattern-based anomaly detector using built-in and custom patterns."""

    def __init__(self, window_seconds: int = 300) -> None:
        self.window_seconds = window_seconds
        init_db()

    def analyze(self, source: str) -> list[dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM log_entries WHERE source = ? AND ingested_at > datetime('now', ? || ' seconds') ORDER BY ingested_at DESC",
            (source, f"-{self.window_seconds}"),
        ).fetchall()
        conn.close()

        findings: list[dict] = []
        for row in rows:
            raw = row["raw"]
            for pattern, category, score in DEFAULT_PATTERNS:
                if re.search(pattern, raw):
                    finding = AnomalyFinding(
                        detector_name=category,
                        source=source,
                        message=f"[{category}] {raw[:200]}",
                        severity="warning" if score < 0.8 else "critical",
                        score=score,
                        details=raw,
                    )
                    finding.save()
                    findings.append({
                        "detector": finding.detector_name,
                        "source": finding.source,
                        "message": finding.message,
                        "severity": finding.severity,
                        "score": finding.score,
                    })
                    break
        return findings


class KeywordSpikeDetector:
    """Detect when a keyword count exceeds a threshold within a time window."""

    def __init__(self, name: str, keywords: list[str], threshold: int = 10, window_s: int = 60) -> None:
        self.name = name
        self.keywords = [k.lower() for k in keywords]
        self.threshold = threshold
        self.window_s = window_s
        self._timestamps: deque[float] = deque()
        init_db()

    def feed(self, entry: LogEntry) -> AnomalyFinding | None:
        lower = entry.raw.lower()
        if not any(k in lower for k in self.keywords):
            return None

        now = datetime.now(timezone.utc).timestamp()
        self._timestamps.append(now)

        cutoff = now - self.window_s
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

        count = len(self._timestamps)
        if count >= self.threshold:
            self._timestamps.clear()
            return AnomalyFinding(
                detector_name=self.name,
                source=entry.source,
                message=f"Keyword spike: {count} matches in {self.window_s}s (threshold={self.threshold})",
                severity="critical" if count >= self.threshold * 2 else "warning",
                score=min(1.0, count / (self.threshold * 2)),
                match_count=count,
                window_s=self.window_s,
            )
        return None


class PatternDetector:
    """Detect custom regex patterns and fire if match count in window exceeds threshold."""

    def __init__(self, name: str, pattern: str, threshold: int = 5, window_s: int = 60) -> None:
        self.name = name
        self.pattern = re.compile(pattern)
        self.threshold = threshold
        self.window_s = window_s
        self._matches: deque[float] = deque()
        init_db()

    def feed(self, entry: LogEntry) -> AnomalyFinding | None:
        if not self.pattern.search(entry.raw):
            return None

        now = datetime.now(timezone.utc).timestamp()
        self._matches.append(now)

        cutoff = now - self.window_s
        while self._matches and self._matches[0] < cutoff:
            self._matches.popleft()

        count = len(self._matches)
        if count >= self.threshold:
            self._matches.clear()
            return AnomalyFinding(
                detector_name=self.name,
                source=entry.source,
                message=f"Pattern spike: '{self.pattern.pattern}' matched {count} times in {self.window_s}s (threshold={self.threshold})",
                severity="critical" if count >= self.threshold * 2 else "warning",
                score=min(1.0, count / (self.threshold * 2)),
                match_count=count,
                window_s=self.window_s,
            )
        return None
