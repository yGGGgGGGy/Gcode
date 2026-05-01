"""Tests for runbook engine."""

import tempfile
from pathlib import Path

from gcode.core.engine import RunbookEngine, Runbook, Step


def test_parse():
    content = """
steps:
  - name: check disk
    command: df -h
    timeout: 10
    retry: 2
  - name: restart nginx
    command: systemctl restart nginx
    rollback: systemctl start nginx
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        tmp = f.name

    try:
        engine = RunbookEngine()
        steps = engine.parse(tmp)
        assert len(steps) == 2
        assert steps[0].name == "check disk"
        assert steps[0].command == "df -h"
        assert steps[0].timeout == 10
        assert steps[0].retry == 2
        assert steps[1].rollback == "systemctl start nginx"
    finally:
        Path(tmp).unlink()


def test_execute_dry():
    engine = RunbookEngine()
    results = engine._run_command("echo hello", 5)
    assert results[0] == 0
    assert "hello" in results[1]
