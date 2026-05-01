"""Tests for logpipe module — engine, detectors, models."""

import json
from pathlib import Path

from gcode.logpipe.engine import Anomaly, LogPipeline
from gcode.logpipe.engine import LogEntry as EngineLogEntry
from gcode.logpipe.detectors import classify_level, evaluate
from gcode.logpipe.models import DetectionHit, DetectionRule, LogEntry, Severity


# ─── LogPipeline (engine) ────────────────────────────────────

class TestLogPipeline:
    def test_ingest_and_query(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:00", "app", "INFO", "hello"))
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:01", "app", "ERROR", "oops"))

        results = pipe.query()
        assert len(results) == 2
        assert results[0].level == "INFO"
        assert results[1].level == "ERROR"

    def test_query_filter_by_level(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:00", "app", "INFO", "ok"))
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:01", "app", "ERROR", "bad"))
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:02", "app", "WARN", "hmm"))

        results = pipe.query(level="ERROR")
        assert len(results) == 1
        assert results[0].message == "bad"

    def test_query_filter_by_source(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:00", "app", "INFO", "a"))
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:01", "sys", "INFO", "b"))

        results = pipe.query(source="sys")
        assert len(results) == 1
        assert results[0].source == "sys"

    def test_query_filter_by_keyword(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:00", "app", "INFO", "connection timeout"))
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:01", "app", "INFO", "all good"))

        results = pipe.query(keyword="timeout")
        assert len(results) == 1
        assert "timeout" in results[0].message

    def test_query_limit(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        for i in range(10):
            pipe.ingest(EngineLogEntry(f"2024-01-01T00:00:{i:02d}", "app", "INFO", f"msg {i}"))

        results = pipe.query(limit=3)
        assert len(results) == 3

    def test_query_empty_file(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "nonexistent.jsonl")
        results = pipe.query()
        assert results == []

    def test_ingest_batch(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        entries = [
            EngineLogEntry("2024-01-01T00:00:00", "app", "INFO", "a"),
            EngineLogEntry("2024-01-01T00:00:01", "app", "WARN", "b"),
        ]
        pipe.ingest_batch(entries)

        results = pipe.query()
        assert len(results) == 2

    def test_stats(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:00", "app", "INFO", "a"))
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:01", "app", "ERROR", "b"))
        pipe.ingest(EngineLogEntry("2024-01-01T00:00:02", "sys", "INFO", "c"))

        s = pipe.stats()
        assert s["total"] == 3
        assert s["by_level"]["INFO"] == 2
        assert s["by_level"]["ERROR"] == 1
        assert s["by_source"]["app"] == 2

    def test_stats_empty(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "nonexistent.jsonl")
        s = pipe.stats()
        assert s["total"] == 0

    def test_detect_anomalies_finds_repeated_errors(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        for i in range(15):
            pipe.ingest(EngineLogEntry(
                f"2024-01-01T00:00:{i:02d}", "app", "ERROR",
                f"connection to db-abc123 failed"
            ))

        anomalies = pipe.detect_anomalies(threshold=10)
        assert len(anomalies) >= 1
        assert anomalies[0].count >= 10

    def test_detect_anomalies_below_threshold(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        for i in range(3):
            pipe.ingest(EngineLogEntry(
                f"2024-01-01T00:00:{i:02d}", "app", "ERROR", "rare error"
            ))

        anomalies = pipe.detect_anomalies(threshold=10)
        assert len(anomalies) == 0

    def test_detect_anomalies_ignores_info(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        for i in range(20):
            pipe.ingest(EngineLogEntry(
                f"2024-01-01T00:00:{i:02d}", "app", "INFO", "normal operation"
            ))

        anomalies = pipe.detect_anomalies(threshold=5)
        assert len(anomalies) == 0

    def test_detect_anomalies_pattern_simplification(self, tmp_path):
        pipe = LogPipeline(storage_path=tmp_path / "logs.jsonl")
        for i in range(12):
            pipe.ingest(EngineLogEntry(
                f"2024-01-01T00:00:{i:02d}", "app", "ERROR",
                f"timeout after {i + 1}ms for request abc123def{i}"
            ))

        anomalies = pipe.detect_anomalies(threshold=10)
        assert len(anomalies) >= 1
        # Hex IDs and numbers should be normalized
        assert "<ID>" in anomalies[0].pattern or "<N>" in anomalies[0].pattern


# ─── Detectors ────────────────────────────────────────────────

class TestClassifyLevel:
    def test_critical(self):
        assert classify_level("CRITICAL: system failure") == "ERROR"

    def test_fatal(self):
        assert classify_level("FATAL panic in kernel") == "ERROR"

    def test_error(self):
        assert classify_level("ERROR: connection refused") == "ERROR"

    def test_err(self):
        assert classify_level("ERR something broke") == "ERROR"

    def test_warn(self):
        assert classify_level("WARN: disk usage high") == "WARN"

    def test_warning(self):
        assert classify_level("WARNING: deprecated API") == "WARN"

    def test_info(self):
        assert classify_level("INFO: server started") == "INFO"

    def test_debug(self):
        assert classify_level("DEBUG: trace output") == "DEBUG"

    def test_unknown(self):
        assert classify_level("just a normal line") is None


class TestEvaluate:
    def test_matching_rule(self):
        entry = LogEntry(source_name="syslog", line="ERROR: disk full on /dev/sda1")
        rule = DetectionRule(name="disk-full", pattern=r"disk full", severity=Severity.ERROR)
        hits = evaluate(entry, [rule])
        assert len(hits) == 1
        assert hits[0].rule == "disk-full"
        assert hits[0].severity == Severity.ERROR

    def test_no_match(self):
        entry = LogEntry(source_name="syslog", line="INFO: all good")
        rule = DetectionRule(name="disk-full", pattern=r"disk full")
        hits = evaluate(entry, [rule])
        assert len(hits) == 0

    def test_disabled_rule_skipped(self):
        entry = LogEntry(source_name="syslog", line="ERROR: disk full")
        rule = DetectionRule(name="disk-full", pattern=r"disk full", enabled=False)
        hits = evaluate(entry, [rule])
        assert len(hits) == 0

    def test_invalid_regex_skipped(self):
        entry = LogEntry(source_name="syslog", line="ERROR: something")
        rule = DetectionRule(name="bad", pattern=r"[invalid")
        hits = evaluate(entry, [rule])
        assert len(hits) == 0

    def test_multiple_rules(self):
        entry = LogEntry(source_name="syslog", line="ERROR: disk full on /dev/sda1")
        rules = [
            DetectionRule(name="disk", pattern=r"disk full"),
            DetectionRule(name="error", pattern=r"ERROR"),
        ]
        hits = evaluate(entry, rules)
        assert len(hits) == 2

    def test_truncates_long_lines(self):
        long_line = "ERROR: " + "x" * 300
        entry = LogEntry(source_name="syslog", line=long_line)
        rule = DetectionRule(name="test", pattern=r"ERROR")
        hits = evaluate(entry, [rule])
        assert len(hits[0].line) <= 200


# ─── Dataclass round-trip ────────────────────────────────────

class TestModels:
    def test_log_entry_defaults(self):
        entry = LogEntry(source_name="app", line="hello")
        assert entry.level is None
        assert entry.parsed_fields is None
        assert entry.ingested_at  # auto-set

    def test_detection_rule_defaults(self):
        rule = DetectionRule(name="test", pattern=r"error")
        assert rule.label == "anomaly"
        assert rule.severity == Severity.WARN
        assert rule.enabled is True

    def test_detection_hit_has_timestamp(self):
        hit = DetectionHit(
            rule="test", severity=Severity.ERROR, label="anomaly",
            source="app", line="ERROR: bad"
        )
        assert hit.detected_at  # auto-set
