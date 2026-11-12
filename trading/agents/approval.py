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
from storage.opportunities import REVISION_KEY

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
        self,
        opportunity_id: str,
        *,
        shown_offer: datetime | None = None,
        shown_revision: str | None = None,
    ) -> ApprovalOutcome:
        """Approve and execute.

        Confirmation callers supply the revision and offer time shown to the
        user. A replacement invalidates that identity even if clocks repeat.
        ID-only callers approve the current offer, which stays pinned to its
        saved revision throughout this call.
        """
        # The offer is read before the Opportunity it covers: if the Agent
        # replaces it in between, the loaded revision will not match.
        offered_revision, offered_at = await self._store.offer_identity(opportunity_id)
        opportunity = await self._store.load(opportunity_id)
        if opportunity is None:
            raise ApprovalRefused("not_found", "Opportunity not found")
        if opportunity.status != OpportunityStatus.PENDING:
            raise ApprovalRefused(
                "not_pending",
                f"Opportunity is {opportunity.status.value}, not pending",
            )
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
        revision = opportunity.data.get(REVISION_KEY)
        if not isinstance(revision, str) or not revision:
            raise ApprovalRefused(
                "not_approvable",
                "Opportunity needs a fresh versioned offer before approval",
            )
        if revision != offered_revision:
            raise ApprovalRefused("changed", _CHANGED)
        quantity = opportunity.suggested_trade.quantity
        if not quantity.is_finite() or quantity < 0:
            raise ApprovalRefused(
                "not_executable", "Opportunity has no usable quantity"
            )
        # A suggestion with no quantity leaves it to sizing.
        ceiling = quantity if quantity > 0 else None
        if shown_offer is not None and offered_at != shown_offer:
            raise ApprovalRefused("changed", _CHANGED)
        if shown_revision is not None and revision != shown_revision:
            raise ApprovalRefused("changed", _CHANGED)
        deadline = opportunity.expires_at or (offered_at + self._max_age)
        if datetime.now(timezone.utc) > deadline:
            if not await self._store.transition(
                opportunity_id,
                OpportunityStatus.PENDING,
                OpportunityStatus.EXPIRED,
                revision=revision,
            ):
                raise ApprovalRefused("changed", _CHANGED)
            raise ApprovalRefused(
                "expired", f"Opportunity expired at {deadline.isoformat()}"
            )
        # Claim it before executing, so a second approval cannot place a second order.
        claim = asyncio.ensure_future(
            self._store.transition(
                opportunity_id,
                OpportunityStatus.PENDING,
                OpportunityStatus.APPROVED,
                revision=revision,
            )
        )
        try:
            claimed = await asyncio.shield(claim)
        except asyncio.CancelledError:
            # Cancelled mid-claim: let the claim land, then give it back.
            await asyncio.wait({claim})
            if not claim.cancelled() and claim.exception() is None and claim.result():
                await self._leave_approved(
                    opportunity_id, OpportunityStatus.PENDING, revision
                )
            raise
        if not claimed:
            row = await self._store.get(opportunity_id)
            if row and row["status"] == OpportunityStatus.PENDING.value:
                raise ApprovalRefused("changed", _CHANGED)
            raise ApprovalRefused("not_pending", "Opportunity is no longer pending")
        opportunity.status = OpportunityStatus.APPROVED
        started = False
        try:
            # A pending Opportunity can be replaced by its Agent. Once claimed
            # it cannot, so confirm the claim took the offer checked above.
            if await self._store.offer_identity(opportunity_id) == (
                revision,
                offered_at,
            ):
                started = True
                # Sizing and risk may reduce the quantity, never raise it above
                # what was approved.
                await self._router.execute(opportunity, max_quantity=ceiling)
        except (Exception, asyncio.CancelledError) as error:
            # The router records what it knows before failing. If it left the
            # status untouched, whether an order went out is not known here, so
            # never report it as rejected. Before execution started, nothing
            # went out and the claim is simply released.
            logger.exception(
                "Approved opportunity %s failed unexpectedly", opportunity_id
            )
            await self._leave_approved(
                opportunity_id,
                OpportunityStatus.RECONCILIATION_REQUIRED
                if started
                else OpportunityStatus.PENDING,
                revision,
            )
            if not started or isinstance(error, asyncio.CancelledError):
                raise
        if not started:
            await self._leave_approved(
                opportunity_id, OpportunityStatus.PENDING, revision
            )
            raise ApprovalRefused("changed", _CHANGED)
        row = await self._store.get(opportunity_id)
        status = OpportunityStatus(row["status"])
        return ApprovalOutcome(opportunity_id, status, _DETAIL.get(status, ""))

    async def _leave_approved(
        self, opportunity_id: str, to: OpportunityStatus, revision: str
    ) -> None:
        # Shielded: a cancellation must not leave the claim in place.
        await asyncio.shield(
            self._store.transition(
                opportunity_id, OpportunityStatus.APPROVED, to, revision=revision
            )
        )
