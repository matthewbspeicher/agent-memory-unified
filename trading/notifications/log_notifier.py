from __future__ import annotations
import logging

from agents.models import Opportunity
from notifications.base import Notifier

logger = logging.getLogger("opportunities")


class LogNotifier(Notifier):
    async def send(self, opportunity: Opportunity) -> None:
        logger.info(
            "[%s] %s %s — confidence=%.0f%% — %s",
            opportunity.agent_name,
            opportunity.signal,
            opportunity.symbol.ticker,
            opportunity.confidence * 100,
            opportunity.reasoning,
        )

    async def send_text(self, message: str) -> None:
        logger.info("[ALERT] %s", message)
