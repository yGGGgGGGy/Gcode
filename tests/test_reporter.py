"""Tests for report generation."""

from gcode.report.reporter import Reporter


def test_generate_daily():
    r = Reporter()
    out = r.generate("daily")
    assert "DAILY" in out
    assert "Service Health" in out
    assert "Alerts Fired" in out
    assert "Log Anomalies" in out


def test_generate_weekly():
    r = Reporter()
    out = r.generate("weekly")
    assert "WEEKLY" in out
    assert "Weekly Summary" in out


def test_generate_incident():
    r = Reporter()
    out = r.generate("incident")
    assert "INCIDENT" in out
    assert "Root Cause Analysis" in out
