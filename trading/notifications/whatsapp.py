from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from agents.models import ActionLevel, Opportunity
from notifications.base import Notifier

if TYPE_CHECKING:
    from whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)


class WhatsAppNotifier(Notifier):
    def __init__(
        self,
        client: WhatsAppClient,
        allowed_numbers: list[str],
        action_level: ActionLevel = ActionLevel.NOTIFY,
    ) -> None:
        self._client = client
        self._allowed_numbers = allowed_numbers
        self._action_level = action_level

    def _format_opportunity(self, opp: Opportunity) -> str:
        lines = [
            f"*{opp.signal}* — {opp.symbol.ticker}",
            f"Agent: {opp.agent_name}",
            f"Confidence: {opp.confidence:.0%}",
            f"Reasoning: {opp.reasoning[:500]}",
        ]
        if opp.suggested_trade:
            t = opp.suggested_trade
            lines.append(f"Trade: {t.side.value} {t.quantity} {t.symbol.ticker}")
        if self._action_level == ActionLevel.SUGGEST_TRADE:
            lines.append(f"\nReply APPROVE {opp.id} to execute")
            lines.append(f"Reply REJECT {opp.id} to dismiss")
        elif opp.status.value == "executed" and opp.suggested_trade:
            t = opp.suggested_trade
            lines.append(f"\nExecuted: {t.side.value} {t.quantity} {t.symbol.ticker}")
        return "\n".join(lines)

    async def send(self, opportunity: Opportunity) -> None:
        if not self._allowed_numbers:
            return

        msg = self._format_opportunity(opportunity)

        for phone in self._allowed_numbers:
            if self._client.is_within_window(phone):
                await self._client.send_text(phone, msg)
            else:
                if self._action_level == ActionLevel.SUGGEST_TRADE:
                    template = "opportunity_approval"
                    params = [
                        opportunity.agent_name,
                        opportunity.symbol.ticker,
                        opportunity.signal,
                        f"{opportunity.confidence:.0%}",
                        opportunity.id,
                        f"Reply APPROVE {opportunity.id} to execute",
                    ]
                else:
                    template = "opportunity_alert"
                    params = [
                        opportunity.agent_name,
                        opportunity.symbol.ticker,
                        opportunity.signal,
                        f"{opportunity.confidence:.0%}",
                    ]
                await self._client.send_template(phone, template, params)

    async def send_text(self, message: str) -> None:
        """Send a plain-text alert to the first allowed number."""
        if not self._allowed_numbers:
            return
        to = self._allowed_numbers[0]
        try:
            await self._client.send_text(to=to, body=message)
        except Exception:
            logger.exception("WhatsAppNotifier.send_text failed")
