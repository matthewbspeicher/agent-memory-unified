from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

from notifications.base import Notifier
from utils.logging import log_event


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CostAlertData:
    global_spend_cents: float
    budget_cents: float
    percent_used: float
    top_agent: str
    top_agent_spend_cents: float
    provider_breakdown: dict[str, float]
    grace_deadline: datetime | None
    window_reset_at: datetime


def _format_cents(value: float) -> str:
    return f"${value / 100:.2f}"


def _format_datetime(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "n/a"


def _format_message(event_type: str, data: CostAlertData) -> str:
    provider_lines = ["Provider breakdown:"]
    if data.provider_breakdown:
        for provider, spend_cents in sorted(
            data.provider_breakdown.items(), key=lambda item: item[1], reverse=True
        ):
            provider_lines.append(f"- {provider}: {_format_cents(spend_cents)}")
    else:
        provider_lines.append("- n/a")

    return "\n".join(
        [
            f"[Cost {event_type}] {data.percent_used:.1f}% of budget used",
            f"Spend: {_format_cents(data.global_spend_cents)} / {_format_cents(data.budget_cents)}",
            f"Top agent: {data.top_agent} ({_format_cents(data.top_agent_spend_cents)})",
            *provider_lines,
            f"Grace deadline: {_format_datetime(data.grace_deadline)}",
            f"Window reset: {_format_datetime(data.window_reset_at)}",
        ]
    )


async def notify_cost_event(
    event_type: str,
    data: CostAlertData,
    notifier: Notifier | None = None,
) -> None:
    level = logging.WARNING if "warning" in event_type.lower() else logging.CRITICAL
    message = _format_message(event_type, data)

    log_event(
        logger,
        level,
        event_type,
        message,
        data={
            "global_spend_cents": data.global_spend_cents,
            "budget_cents": data.budget_cents,
            "percent_used": data.percent_used,
            "top_agent": data.top_agent,
            "top_agent_spend_cents": data.top_agent_spend_cents,
            "provider_breakdown": data.provider_breakdown,
            "grace_deadline": data.grace_deadline.isoformat()
            if data.grace_deadline
            else None,
            "window_reset_at": data.window_reset_at.isoformat(),
        },
    )

    if notifier is not None:
        await notifier.send_text(message)
