from __future__ import annotations

import logging
import httpx
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any

from notifications.base import Notifier
from agents.models import ActionLevel, Opportunity

logger = logging.getLogger(__name__)


def _format_price(value: Any) -> str:
    if isinstance(value, (int, float, Decimal)):
        return f"${value:.2f}"
    return "N/A"


class DiscordNotifier(Notifier):
    """Sends real-time trading events and system logs to a Discord webhook."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url

    async def send(self, opportunity: Opportunity) -> None:
        """Send a notification for a specific trading opportunity."""
        title = f"🚀 Trading Opportunity: {opportunity.symbol}"
        strategy = str(opportunity.data.get("strategy", opportunity.agent_name))
        side = opportunity.signal
        entry_price = opportunity.data.get("entry_price")
        stop_loss = opportunity.data.get("stop_loss")
        take_profit = opportunity.data.get("take_profit")
        level = (
            ActionLevel.AUTO_EXECUTE
            if opportunity.suggested_trade is not None
            else ActionLevel.SUGGEST_TRADE
        )
        message = (
            f"Strategy: {strategy}\n"
            f"Side: {side}\n"
            f"Price: {_format_price(entry_price)}\n"
            f"Confidence: {opportunity.confidence:.2%}"
        )
        await self.notify(
            title=title,
            message=message,
            level=level,
            metadata={
                "Symbol": opportunity.symbol,
                "Strategy": strategy,
                "Side": side,
                "Entry": _format_price(entry_price),
                "Stop": _format_price(stop_loss),
                "Target": _format_price(take_profit),
            },
        )

    async def send_text(self, message: str) -> None:
        """Send a plain text alert."""
        await self.notify(title="System Alert", message=message)

    async def notify(
        self,
        title: str,
        message: str,
        level: ActionLevel = ActionLevel.NOTIFY,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.webhook_url:
            return

        # Map levels to colors (Hex)
        color_map = {
            ActionLevel.NOTIFY: 0x3498DB,  # Blue
            ActionLevel.SUGGEST_TRADE: 0xF1C40F,  # Yellow
            ActionLevel.AUTO_EXECUTE: 0x2ECC71,  # Green
        }
        color = color_map.get(level, 0x95A5A6)  # Gray fallback

        embed = {
            "title": title,
            "description": message,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Agent Memory Commons - Mission Control"},
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
