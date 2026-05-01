"""Tests for monitor module -- checkers and evaluator."""

import tempfile
from pathlib import Path

from gcode.monitor.checkers import Checker, CheckResult
from gcode.monitor.evaluator import Evaluator, MonitorConfig


def test_check_result_fields():
    r = CheckResult("test", "ok", 1.5, "fine")
    assert r.name == "test"
    assert r.status == "ok"
    assert r.latency_ms == 1.5
    assert r.message == "fine"


def test_check_result_fail():
    r = CheckResult("test", "fail", 0, "broken")
    assert r.status == "fail"


def test_checker_http_ok():
    # Test with a known-unreachable URL to verify graceful failure
    r = Checker.http("http://localhost:1", timeout=1)
    assert r.status == "fail"
    assert r.latency_ms >= 0


def test_checker_tcp_unreachable():
    r = Checker.tcp("localhost", 1, timeout=1)
    assert r.status == "fail"
    assert r.name == "localhost:1"


def test_checker_process_nonexistent():
    r = Checker.process("definitely_not_a_real_process_name_12345")
    assert r.status == "fail"
    assert "Not running" in r.message


def test_checker_disk():
    r = Checker.disk("/")
    assert r.status in ("ok", "warn", "fail")
    assert "Disk" in r.message


def test_checker_memory():
    r = Checker.memory()
    assert r.status in ("ok", "warn", "fail")
    assert "Memory" in r.message


def test_evaluator_default_checks():
    config = Evaluator.default_checks()
    assert len(config.checks) == 3
    result = Evaluator.run_checks(config)
    assert len(result.results) == 3
    assert result.ok_count + result.warn_count + result.fail_count == 3
    assert result.duration_ms >= 0


def test_evaluator_custom_config():
    config = MonitorConfig(checks=[
        {"type": "disk", "path": "/"},
        {"type": "memory"},
    ])
    result = Evaluator.run_checks(config)
    assert len(result.results) == 2


def test_suite_result_healthy():
    config = MonitorConfig(checks=[
        {"type": "disk", "path": "/"},
    ])
    result = Evaluator.run_checks(config)
    # Disk check on "/" should not fail in test environment
    assert result.healthy == (result.fail_count == 0)
