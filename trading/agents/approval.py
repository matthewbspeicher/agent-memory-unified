"""Approving a suggested Opportunity executes it.

An approved Opportunity takes the same path as one an Agent may execute on its
own: health gate, sizing, risk preview, the execution service, and post-fill
bookkeeping. Approval adds only the checks a human decision needs: it happens
once, and not after the Opportunity has gone stale.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from agents.models import OpportunityStatus

logger = logging.getLogger(__name__)


class ApprovalRefused(Exception):
    """The Opportunity was not approved and nothing was sent to a broker."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        # not_found | not_pending | not_approvable | expired | not_executable | changed
        self.reason = reason
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
        "known. Check it before acting again."
    ),
    OpportunityStatus.REJECTED: "Approved, but the order was not placed or was rejected.",
    OpportunityStatus.APPROVED: (
        "Approved, but no order was confirmed. The Agent may be in shadow "
        "mode, or execution stopped before submitting. Check it before "
        "acting again."
    ),
}


_CHANGED = "Opportunity changed while it was being approved. Review it again"


class OpportunityApprover:
    def __init__(self, store, router, *, max_age: timedelta) -> None:
        self._store = store
        # A consensus wrapper routes; only the router beneath it executes.
        self._router = getattr(router, "_target", router)
        self._max_age = max_age

    async def approve(
        self, opportunity_id: str, *, shown_offer: datetime | None = None
    ) -> ApprovalOutcome:
        """Approve and execute.

        shown_offer is the offer time of the Opportunity the approver was
        shown. Replacing an Opportunity withdraws its offer and every offer
        has its own time, so a different one means the order, broker, exit or
        expiry may no longer be what was shown, and the approval is refused.
        """
        opportunity = await self._store.load(opportunity_id)
        if opportunity is None:
            raise ApprovalRefused("not_found", "Opportunity not found")
        if opportunity.status != OpportunityStatus.PENDING:
            raise ApprovalRefused(
                "not_pending",
                f"Opportunity is {opportunity.status.value}, not pending",
            )
        offered_at = await self._store.offered_at(opportunity_id)
        if offered_at is None:
            raise ApprovalRefused(
                "not_approvable",
                "Opportunity was not offered for approval. Its Agent may only "
                "notify, or a gate held it back.",
            )
        if opportunity.suggested_trade is None:
            raise ApprovalRefused(
                "not_executable",
                "Opportunity has no stored order to execute. It proposed no "
                "trade, or was saved before approvals placed orders.",
            )
        if shown_offer is not None and offered_at != shown_offer:
            raise ApprovalRefused("changed", _CHANGED)
        deadline = opportunity.expires_at or (offered_at + self._max_age)
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
        quantity = opportunity.suggested_trade.quantity
        started = False
        try:
            # A pending Opportunity can be replaced by its Agent. Once claimed
            # it cannot, so confirm the claim took the offer checked above.
            if await self._store.offered_at(opportunity_id) == offered_at:
                started = True
                # Sizing and risk may reduce the quantity, never raise it above
                # what was approved. A suggestion with no quantity leaves it
                # to sizing.
                await self._router.execute(
                    opportunity, max_quantity=quantity if quantity > 0 else None
                )
        except (Exception, asyncio.CancelledError) as error:
            # The router records what it knows before failing. If it left the
            # status untouched, whether an order went out is not known here, so
            # never report it as rejected. Before execution started, nothing
            # went out and the claim is simply released.
            logger.exception("Approved opportunity %s failed unexpectedly", opportunity_id)
            await self._leave_approved(
                opportunity_id,
                OpportunityStatus.RECONCILIATION_REQUIRED
                if started
                else OpportunityStatus.PENDING,
            )
            if not started or isinstance(error, asyncio.CancelledError):
                raise
        if not started:
            await self._leave_approved(opportunity_id, OpportunityStatus.PENDING)
            raise ApprovalRefused("changed", _CHANGED)
        row = await self._store.get(opportunity_id)
        status = OpportunityStatus(row["status"])
        return ApprovalOutcome(opportunity_id, status, _DETAIL.get(status, ""))

    async def _leave_approved(self, opportunity_id: str, to: OpportunityStatus) -> None:
        # Shielded: a cancellation must not leave the claim in place.
        await asyncio.shield(
            self._store.transition(opportunity_id, OpportunityStatus.APPROVED, to)
        )
