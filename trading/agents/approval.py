"""Approving a suggested Opportunity executes it.

An approved Opportunity takes the same path as one an Agent may execute on its
own: health gate, sizing, risk preview, the execution service, and post-fill
bookkeeping. Approval adds only the checks a human decision needs: it happens
once, and not after the Opportunity has gone stale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from agents.models import OpportunityStatus

logger = logging.getLogger(__name__)


class ApprovalRefused(Exception):
    """The Opportunity was not approved and nothing was sent to a broker."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason  # not_found | not_pending | expired | not_executable
        self.detail = detail


@dataclass(frozen=True)
class ApprovalOutcome:
    opportunity_id: str
    status: OpportunityStatus
    detail: str


_DETAIL = {
    OpportunityStatus.EXECUTED: "Order filled.",
    OpportunityStatus.RECONCILIATION_REQUIRED: (
        "Order accepted but not completely filled, or its outcome is not yet "
        "known. It is awaiting fill reconciliation."
    ),
    OpportunityStatus.REJECTED: "Approved, but the order was not placed or was rejected.",
    OpportunityStatus.APPROVED: (
        "Approved, but no order was placed. The Agent may be in shadow mode."
    ),
}


class OpportunityApprover:
    def __init__(self, store, router, *, max_age: timedelta) -> None:
        self._store = store
        # A consensus wrapper routes; only the router beneath it executes.
        self._router = getattr(router, "_target", router)
        self._max_age = max_age

    async def approve(self, opportunity_id: str) -> ApprovalOutcome:
        opportunity = await self._store.load(opportunity_id)
        if opportunity is None:
            raise ApprovalRefused("not_found", "Opportunity not found")
        if opportunity.status != OpportunityStatus.PENDING:
            raise ApprovalRefused(
                "not_pending",
                f"Opportunity is {opportunity.status.value}, not pending",
            )
        if opportunity.suggested_trade is None:
            raise ApprovalRefused(
                "not_executable",
                "Opportunity has no stored order to execute. It proposed no "
                "trade, or was saved before approvals placed orders.",
            )
        deadline = opportunity.expires_at or (opportunity.timestamp + self._max_age)
        if datetime.now(timezone.utc) > deadline:
            await self._store.transition(
                opportunity_id, OpportunityStatus.PENDING, OpportunityStatus.EXPIRED
            )
            raise ApprovalRefused(
                "expired", f"Opportunity expired at {deadline.isoformat()}"
            )
        # Claim it before executing, so a second approval cannot place a second order.
        if not await self._store.transition(
            opportunity_id, OpportunityStatus.PENDING, OpportunityStatus.APPROVED
        ):
            raise ApprovalRefused("not_pending", "Opportunity is no longer pending")
        opportunity.status = OpportunityStatus.APPROVED
        try:
            await self._router.execute(opportunity)
        except Exception:
            # The router guards the submission itself; an error escaping it
            # happened before any order was sent.
            logger.exception("Approved opportunity %s failed before submission", opportunity_id)
            await self._store.transition(
                opportunity_id, OpportunityStatus.APPROVED, OpportunityStatus.REJECTED
            )
        row = await self._store.get(opportunity_id)
        status = OpportunityStatus(row["status"])
        return ApprovalOutcome(opportunity_id, status, _DETAIL.get(status, ""))
