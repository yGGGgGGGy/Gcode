from __future__ import annotations

import json
from .models import get_db


class ChannelRegistry:
    def register(self, name: str, config: dict) -> None:
        conn = get_db()
        existing = conn.execute("SELECT id FROM notification_channels WHERE name = ?", (name,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE notification_channels SET config_json = ? WHERE name = ?",
                (json.dumps(config), name),
            )
        else:
            conn.execute(
                "INSERT INTO notification_channels (name, config_json) VALUES (?, ?)",
                (name, json.dumps(config)),
            )
        conn.commit()
        conn.close()

    def save(self, name: str, config: dict) -> None:
        self.register(name, config)

    def list_all(self) -> list[tuple[str, dict]]:
        conn = get_db()
        rows = conn.execute("SELECT name, config_json FROM notification_channels WHERE enabled = 1").fetchall()
        conn.close()
        return [(r["name"], json.loads(r["config_json"])) for r in rows]

    def get(self, name: str) -> dict | None:
        conn = get_db()
        row = conn.execute("SELECT config_json FROM notification_channels WHERE name = ? AND enabled = 1", (name,)).fetchone()
        conn.close()
        if row:
            return json.loads(row["config_json"])
        return None

    def notify(self, channel_name: str, message: str) -> bool:
        config = self.get(channel_name)
        if config is None:
            return False
        if "webhook_url" in config:
            return self._notify_webhook(config["webhook_url"], message)
        return False

    def _notify_webhook(self, url: str, message: str) -> bool:
        import urllib.request
        data = json.dumps({"text": message}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False
