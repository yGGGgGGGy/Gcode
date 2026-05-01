import click
from .engine import AlertEngine
from .router import AlertRouter
from .channels import ChannelRegistry

__all__ = ["AlertEngine", "AlertRouter", "ChannelRegistry", "register_commands"]


def register_commands(cli: click.Group) -> None:
    @cli.group()
    def alert():
        """Alert management and notification routing."""

    @alert.command()
    @click.option("--name", required=True, help="Alert rule name")
    @click.option("--metric", required=True, help="Metric to watch")
    @click.option("--above", type=float, help="Fire when metric exceeds this value")
    @click.option("--below", type=float, help="Fire when metric drops below this value")
    def rule(name, metric, above, below):
        """Define an alert rule."""
        from .models import AlertRule
        rule_obj = AlertRule(name=name, metric=metric, threshold_gt=above, threshold_lt=below)
        rule_obj.save()
        click.echo(f"Rule '{name}' created (id={rule_obj.id}).")

    @alert.command()
    @click.option("--rule", "rule_id", type=int, help="Filter by rule id")
    @click.option("--target", help="Filter by target")
    @click.option("--limit", type=int, default=20)
    def fired(rule_id, target, limit):
        """List recent alert firings."""
        from .models import AlertEvent, get_db
        conn = get_db()
        query = "SELECT * FROM alert_events WHERE 1=1"
        params: list = []
        if rule_id is not None:
            query += " AND rule_id = ?"
            params.append(rule_id)
        if target:
            query += " AND target = ?"
            params.append(target)
        query += " ORDER BY fired_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        for r in rows:
            status_icon = "ACK" if r["acked"] else "NEW"
            click.echo(f"[{r['id']}] {status_icon} {r['rule_name']} on {r['target']}: {r['message']} ({r['fired_at']})")

    @alert.command()
    @click.argument("alert_id", type=int)
    def ack(alert_id):
        """Acknowledge an alert."""
        from .models import AlertEvent, get_db
        conn = get_db()
        conn.execute("UPDATE alert_events SET acked = 1 WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()
        click.echo(f"Alert {alert_id} acknowledged.")

    @alert.command()
    @click.option("--channel", required=True, help="Notification channel name")
    @click.option("--config", required=True, help="Channel config as JSON string, e.g. '{\"webhook_url\":\"...\"}'")
    def channel(channel, config):
        """Register a notification channel."""
        import json
        registry = ChannelRegistry()
        cfg = json.loads(config)
        registry.register(channel, cfg)
        registry.save(channel, cfg)
        click.echo(f"Channel '{channel}' registered.")

    @alert.command()
    def channels():
        """List registered notification channels."""
        from .channels import ChannelRegistry
        registry = ChannelRegistry()
        for name, cfg in registry.list_all():
            click.echo(f"{name}: {cfg}")
