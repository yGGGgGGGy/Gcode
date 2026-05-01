"""Tests for alert module -- engine, rules, lifecycle."""

import tempfile
from pathlib import Path

from gcode.alert.engine import AlertEngine, Severity, Alert


def test_fire_alert():
    with tempfile.TemporaryDirectory() as d:
        storage = Path(d) / "alerts.json"
        engine = AlertEngine(storage_path=storage)
        alert = engine.fire(
            title="Test alert",
            severity=Severity.WARN,
            source="test",
            message="Something happened",
        )
        assert alert.id.startswith("ALERT-")
        assert alert.title == "Test alert"
        assert alert.severity == Severity.WARN
        assert not alert.acknowledged
        assert not alert.resolved


def test_active_alerts():
    with tempfile.TemporaryDirectory() as d:
        storage = Path(d) / "alerts.json"
        engine = AlertEngine(storage_path=storage)
        engine.fire("A", Severity.INFO, "test", "msg1")
        engine.fire("B", Severity.WARN, "test", "msg2")
        assert len(engine.active()) == 2


def test_ack_alert():
    with tempfile.TemporaryDirectory() as d:
        storage = Path(d) / "alerts.json"
        engine = AlertEngine(storage_path=storage)
        alert = engine.fire("Test", Severity.WARN, "test", "msg")
        assert engine.ack(alert.id)
        assert engine.active()[0].acknowledged
        assert not engine.ack("nonexistent-id")


def test_resolve_alert():
    with tempfile.TemporaryDirectory() as d:
        storage = Path(d) / "alerts.json"
        engine = AlertEngine(storage_path=storage)
        alert = engine.fire("Test", Severity.CRITICAL, "test", "msg")
        assert engine.resolve(alert.id)
        assert len(engine.active()) == 0
        assert not engine.resolve("nonexistent-id")


def test_summary():
    with tempfile.TemporaryDirectory() as d:
        storage = Path(d) / "alerts.json"
        engine = AlertEngine(storage_path=storage)
        engine.fire("A", Severity.WARN, "test", "msg")
        engine.fire("B", Severity.CRITICAL, "test", "msg")
        alert_c = engine.fire("C", Severity.INFO, "test", "msg")
        engine.resolve(alert_c.id)
        s = engine.summary()
        assert s["total_fired"] == 3
        assert s["active"] == 2
        assert s["by_severity"]["warn"] == 1
        assert s["by_severity"]["critical"] == 1
        assert s["by_severity"]["info"] == 0


def test_persistence():
    with tempfile.TemporaryDirectory() as d:
        storage = Path(d) / "alerts.json"
        engine1 = AlertEngine(storage_path=storage)
        engine1.fire("Persistent", Severity.WARN, "test", "msg")
        # Reload from same storage
        engine2 = AlertEngine(storage_path=storage)
        assert len(engine2.active()) == 1
        assert engine2.active()[0].title == "Persistent"


def test_severity_from_json():
    """Verify severity is correctly deserialized as enum after JSON round-trip."""
    with tempfile.TemporaryDirectory() as d:
        storage = Path(d) / "alerts.json"
        engine1 = AlertEngine(storage_path=storage)
        engine1.fire("S1", Severity.INFO, "test", "msg")
        engine1.fire("S2", Severity.CRITICAL, "test", "msg")
        engine2 = AlertEngine(storage_path=storage)
        for a in engine2.active():
            assert isinstance(a.severity, Severity)
            assert a.severity.value in ("info", "warn", "critical")
