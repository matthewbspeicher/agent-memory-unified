import hashlib
import hmac as hmac_mod
import inspect
import logging
import time

import httpx

from agents.models import Opportunity
from notifications.base import Notifier

logger = logging.getLogger(__name__)


def _sign_action(api_key: str, opportunity_id: str, action: str) -> tuple[str, int]:
    ts = int(time.time())
    payload = f"{opportunity_id}:{action}:{ts}"
    sig = hmac_mod.new(api_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return sig, ts


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str, api_base_url: str | None = None, api_key: str = ""):
        self.webhook_url = webhook_url
        self.api_base_url = api_base_url
        self._api_key = api_key

    async def send(self, opportunity: Opportunity) -> None:
        if not self.webhook_url:
            return

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"New Trading Opportunity: {opportunity.symbol.ticker}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Agent:*\n{opportunity.agent_name}"},
                    {"type": "mrkdwn", "text": f"*Signal:*\n{opportunity.signal}"},
                    {"type": "mrkdwn", "text": f"*Confidence:*\n{opportunity.confidence:.2f}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{opportunity.status}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Reasoning:*\n{opportunity.reasoning}"},
            },
        ]

        if self.api_base_url and self._api_key:
            approve_sig, approve_ts = _sign_action(self._api_key, str(opportunity.id), "approve")
            reject_sig, reject_ts = _sign_action(self._api_key, str(opportunity.id), "reject")
            approve_url = (
                f"{self.api_base_url}/opportunities/{opportunity.id}/approve"
                f"?ts={approve_ts}&sig={approve_sig}"
            )
            reject_url = (
                f"{self.api_base_url}/opportunities/{opportunity.id}/reject"
                f"?ts={reject_ts}&sig={reject_sig}"
            )
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "approve_opp",
                        "url": approve_url,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "reject_opp",
                        "url": reject_url,
                    },
                ],
            })

        payload = {"blocks": blocks}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(self.webhook_url, json=payload)
                maybe_awaitable = r.raise_for_status()
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable
        except Exception as exc:
            logger.warning("Slack notification failed: %s", exc)
