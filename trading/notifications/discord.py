from __future__ import annotations

import logging
import httpx
from datetime import datetime, timezone
from typing import Any

from notifications.base import Notifier
from agents.models import ActionLevel, Opportunity

logger = logging.getLogger(__name__)

class DiscordNotifier(Notifier):
    """Sends real-time trading events and system logs to a Discord webhook."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url

    async def send(self, opportunity: Opportunity) -> None:
        """Send a notification for a specific trading opportunity."""
        title = f"🚀 Trading Opportunity: {opportunity.symbol}"
        message = (
            f"Strategy: {opportunity.strategy}\n"
            f"Side: {opportunity.side.value}\n"
            f"Price: ${opportunity.entry_price:.2f}\n"
            f"Confidence: {opportunity.confidence:.2%}"
        )
        await self.notify(
            title=title,
            message=message,
            level=opportunity.action_level,
            metadata={
                "Symbol": opportunity.symbol,
                "Entry": str(opportunity.entry_price),
                "Stop": str(opportunity.stop_loss),
                "Target": str(opportunity.take_profit),
            }
        )

    async def send_text(self, message: str) -> None:
        """Send a plain text alert."""
        await self.notify(title="System Alert", message=message)

    async def notify(
        self, 
        title: str, 
        message: str, 
        level: ActionLevel = ActionLevel.NOTIFY,
        metadata: dict[str, Any] | None = None
    ) -> None:
        if not self.webhook_url:
            return

        # Map levels to colors (Hex)
        color_map = {
            ActionLevel.NOTIFY: 0x3498db,    # Blue
            ActionLevel.SUGGEST_TRADE: 0xf1c40f, # Yellow
            ActionLevel.EXECUTE_TRADE: 0x2ecc71, # Green
        }
        color = color_map.get(level, 0x95a5a6) # Gray fallback

        embed = {
            "title": title,
            "description": message,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Agent Memory Commons - Mission Control"}
        }

        if metadata:
            fields = []
            for key, val in metadata.items():
                fields.append({"name": key, "value": str(val), "inline": True})
            embed["fields"] = fields

        payload = {"embeds": [embed]}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json=payload, timeout=5.0)
                resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to send Discord notification: %s", e)
