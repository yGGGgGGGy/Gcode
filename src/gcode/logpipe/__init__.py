"""Log pipeline — ingest, parse, detect anomalies."""

from __future__ import annotations

import click

from .sources import FileTailSource, StdinSource, JournaldSource
from .parser import ParserChain
from .detector import AnomalyDetector, KeywordSpikeDetector, PatternDetector

__all__ = [
    "FileTailSource", "StdinSource", "JournaldSource",
    "ParserChain",
    "AnomalyDetector", "KeywordSpikeDetector", "PatternDetector",
    "register_commands",
]


def register_commands(cli: click.Group) -> None:
    @cli.group()
    def logpipe():
        """Log ingestion, parsing and anomaly detection."""

    # -- Source management --

    @logpipe.command()
    @click.argument("source_name")
    @click.option("--type", "source_type", type=click.Choice(["file", "stdin"]), default="file")
    @click.option("--path", help="File path (for file source)")
    def source(source_name, source_type, path):
        """Register a log source."""
        from .models import LogSourceModel, init_db

        init_db()
        s = LogSourceModel(name=source_name, source_type=source_type, config={"path": path or ""})
        s.save()
        click.echo(f"Log source '{source_name}' registered (id={s.id}).")

    # -- Ingestion --

    @logpipe.command()
    @click.argument("source_name")
    @click.option("--file", "file_path", help="Direct file path (overrides source config)")
    @click.option("--head", type=int, default=50, help="Lines to read")
    def tail(source_name, file_path, head):
        """Tail a log source and ingest recent lines."""
        path = file_path or source_name
        source = FileTailSource(path, label=source_name)
        chain = ParserChain()
        count = 0
        for entry in source.tail():
            entry = chain.apply(entry)
            entry.save()
            click.echo(f"[{entry.level or 'unknown':>8}] {entry.message or entry.raw}")
            count += 1
            if count >= head:
                break
        click.echo(f"\nIngested {count} lines from {source_name}.")

    @logpipe.command()
    @click.option("--head", type=int, default=50, help="Lines to read")
    def tap(head):
        """Read log lines from stdin and ingest."""
        source = StdinSource()
        chain = ParserChain()
        count = 0
        for entry in source.read():
            entry = chain.apply(entry)
            entry.save()
            click.echo(f"[{entry.level or 'unknown':>8}] {entry.message or entry.raw}")
            count += 1
            if count >= head:
                break
        click.echo(f"\nIngested {count} lines from stdin.")

    @logpipe.command()
    @click.option("--unit", help="Systemd unit to filter")
    @click.option("--lines", type=int, default=50, help="Journal lines to fetch")
    def journal(unit, lines):
        """Query systemd journal and ingest entries."""
        source = JournaldSource(unit=unit)
        chain = ParserChain()
        count = 0
        for entry in source.query(lines=lines):
            entry = chain.apply(entry)
            entry.save()
            click.echo(f"[{entry.level or 'unknown':>8}] {entry.message or entry.raw}")
            count += 1
        click.echo(f"\nIngested {count} lines from journal.")

    # -- Parse rules --

    @logpipe.command()
    @click.option("--name", required=True, help="Parse rule name")
    @click.option("--pattern", required=True, help="Regex pattern with named groups")
    @click.option("--type", "pattern_type", type=click.Choice(["regex", "json", "syslog"]), default="regex")
    @click.option("--source-filter", default="*", help="Glob or substring filter on source name")
    @click.option("--field-map", default="{}", help="JSON map of group names to field names")
    def add_rule(name, pattern, pattern_type, source_filter, field_map):
        """Add a log parse rule."""
        import json

        from .models import ParseRule, init_db

        init_db()
        rule = ParseRule(
            name=name,
            source_filter=source_filter,
            pattern=pattern,
            pattern_type=pattern_type,
            field_map=json.loads(field_map),
        )
        rule.save()
        click.echo(f"Parse rule '{name}' added (id={rule.id}).")

    @logpipe.command()
    def list_rules():
        """List all parse rules."""
        from .models import get_db

        conn = get_db()
        rows = conn.execute("SELECT * FROM parse_rules ORDER BY id").fetchall()
        conn.close()
        if not rows:
            click.echo("No parse rules defined.")
            return
        for r in rows:
            state = "ON" if r["enabled"] else "OFF"
            click.echo(f"[{state}] {r['id']}: {r['name']} ({r['pattern_type']}) — {r['pattern']}")

    @logpipe.command()
    @click.argument("rule_id", type=int)
    @click.option("--enable/--disable", default=True)
    def toggle_rule(rule_id, enable):
        """Enable or disable a parse rule."""
        from .models import get_db

        conn = get_db()
        conn.execute("UPDATE parse_rules SET enabled = ? WHERE id = ?", (int(enable), rule_id))
        conn.commit()
        conn.close()
        click.echo(f"Rule {rule_id} {'enabled' if enable else 'disabled'}.")

    # -- Anomaly detection --

    @logpipe.command()
    @click.argument("source_name")
    @click.option("--window", type=int, default=300, help="Analysis window in seconds")
    def analyze(source_name, window):
        """Run built-in anomaly detection on a log source."""
        detector = AnomalyDetector(window_seconds=window)
        findings = detector.analyze(source_name)
        if findings:
            for f in findings:
                click.echo(f"[{f['severity'].upper()}] {f['detector']}: {f['message']} (score: {f['score']})")
        else:
            click.echo("No anomalies detected.")

    @logpipe.command()
    @click.option("--detector", required=True, help="Detector name")
    @click.option("--keywords", required=True, help="Comma-separated keywords")
    @click.option("--threshold", type=int, default=10)
    @click.option("--window", type=int, default=60, help="Window in seconds")
    def run_keyword(detector, keywords, threshold, window):
        """Run a keyword spike detector against recent logs."""
        from .models import get_db

        kw = [k.strip() for k in keywords.split(",")]
        d = KeywordSpikeDetector(name=detector, keywords=kw, threshold=threshold, window_s=window)
        conn = get_db()
        rows = conn.execute("SELECT * FROM log_entries ORDER BY ingested_at DESC LIMIT 500").fetchall()
        conn.close()
        hits = 0
        for r in rows:
            entry = LogEntry(source=r["source"], raw=r["raw"], level=r["level"], message=r["message"])
            result = d.feed(entry)
            if result:
                result.save()
                click.echo(f"ANOMALY: {result.message}")
                hits += 1
        click.echo(f"Done — {hits} anomalies detected.")

    @logpipe.command()
    @click.option("--detector", required=True, help="Detector name")
    @click.option("--pattern", required=True, help="Regex pattern")
    @click.option("--threshold", type=int, default=5)
    @click.option("--window", type=int, default=60, help="Window in seconds")
    def run_pattern(detector, pattern, threshold, window):
        """Run a custom pattern detector against recent logs."""
        from .models import get_db

        d = PatternDetector(name=detector, pattern=pattern, threshold=threshold, window_s=window)
        conn = get_db()
        rows = conn.execute("SELECT * FROM log_entries ORDER BY ingested_at DESC LIMIT 500").fetchall()
        conn.close()
        hits = 0
        for r in rows:
            entry = LogEntry(source=r["source"], raw=r["raw"])
            result = d.feed(entry)
            if result:
                result.save()
                click.echo(f"ANOMALY: {result.message}")
                hits += 1
        click.echo(f"Done — {hits} anomalies detected.")

    @logpipe.command()
    @click.option("--limit", type=int, default=20)
    def recent(limit):
        """Show recently detected anomalies."""
        from .models import get_db

        conn = get_db()
        rows = conn.execute("SELECT * FROM anomaly_findings ORDER BY detected_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        if not rows:
            click.echo("No anomalies detected.")
            return
        for r in rows:
            click.echo(f"[{r['severity'].upper()}] {r['detector_name']}: {r['message']} (score={r['score']}, count={r['match_count']})")
