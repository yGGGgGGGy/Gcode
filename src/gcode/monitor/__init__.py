import click
from .collector import Collector
from .checker import HealthChecker
from .threshold import ThresholdEngine

__all__ = ["Collector", "HealthChecker", "ThresholdEngine", "register_commands"]


def register_commands(cli: click.Group) -> None:
    @cli.group()
    def monitor():
        """Service health monitoring and metrics collection."""

    @monitor.command()
    @click.argument("target")
    @click.option("--type", "check_type", type=click.Choice(["http", "tcp", "process"]), default="http")
    @click.option("--interval", type=int, default=30, help="Check interval in seconds")
    @click.option("--timeout", type=int, default=5, help="Check timeout in seconds")
    def check(target, check_type, interval, timeout):
        """Run a health check against TARGET."""
        checker = HealthChecker(timeout=timeout)
        result = checker.run(target, check_type)
        click.echo(f"{target}: {'OK' if result.healthy else 'FAIL'} ({result.latency_ms}ms)")

    @monitor.command()
    @click.argument("target")
    @click.option("--metric", multiple=True, help="Metrics to collect (cpu, mem, disk, load)")
    def collect(target, metric):
        """Collect metrics from TARGET."""
        collector = Collector(metrics=list(metric) or ["cpu", "mem"])
        results = collector.collect(target)
        for k, v in results.items():
            click.echo(f"{k}: {v}")

    @monitor.command()
    @click.argument("target")
    @click.option("--cpu", type=float, help="CPU threshold percent")
    @click.option("--mem", type=float, help="Memory threshold percent")
    @click.option("--disk", type=float, help="Disk threshold percent")
    def watch(target, cpu, mem, disk):
        """Watch TARGET and alert on threshold breaches."""
        thresholds = {}
        if cpu: thresholds["cpu"] = cpu
        if mem: thresholds["mem"] = mem
        if disk: thresholds["disk"] = disk
        engine = ThresholdEngine(thresholds)
        breaches = engine.evaluate(target)
        if breaches:
            for b in breaches:
                click.echo(f"BREACH: {b.metric} = {b.value} (threshold: {b.threshold})")
        else:
            click.echo("All clear.")
