"""Provision / revoke paid-subscriber agents in the identity store.

Spec §6: each successful Stripe checkout creates an identity-store agent
named `feed_sub_<stripe_customer_id>` with scope `read:feeds.arb`. Each
`customer.subscription.deleted` webhook revokes that agent (keeps the
record for audit trail; just sets revoked_at).

This module is the seam between Stripe events and the agent runtime:
it mints a token, stores its hash, and returns the plain token so the
caller can email it to the subscriber. The token is NEVER persisted in
plain text anywhere — if the email step fails we log enough to operator-
recover (audit entry + customer id) but the subscriber must be re-onboarded.

Refactored out of trading/api/routes/billing/webhooks.py so the same
provisioning logic is reachable from:
  - The webhook handler (primary)
  - The hourly reconciliation job (catches missed webhooks)
  - The admin POST /api/v1/admin/billing/reconcile escape-hatch
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from api.identity.tokens import generate_token, hash_token
from utils.logging import log_event

if TYPE_CHECKING:
    from api.identity.store import IdentityStore

logger = logging.getLogger(__name__)


# Spec §6: agent name pattern. Deterministic from Stripe customer id so
# the same customer re-subscribing finds their prior agent record.
AGENT_NAME_PREFIX = "feed_sub_"
SUBSCRIBER_SCOPE = "read:feeds.arb"
# Rate-limit tier key; the tier-resolver in api/middleware/limiter.py
# maps this to the 600/hr allowance (spec §3.2).
SUBSCRIBER_TIER = "feed_sub"


def agent_name_for_customer(stripe_customer_id: str) -> str:
    """Deterministic: customer -> agent name. Used by provision() and the
    reconciliation job to look the record up without a Stripe-id column
    on identity.agents."""
    return f"{AGENT_NAME_PREFIX}{stripe_customer_id}"


@dataclass
class ProvisionResult:
    """Returned to the webhook handler so it can surface the plain token
    via whatever delivery mechanism is wired (email today, dashboard
    later). `token` is `None` for idempotent re-runs where the agent
    already exists — a new token should NOT be minted in that case; the
    subscriber still has the original."""

    agent_name: str
    token: str | None
    created: bool


async def provision_subscriber(
    store: "IdentityStore",
    *,
    stripe_customer_id: str,
    contact_email: str | None,
    actor: str = "stripe_webhook",
) -> ProvisionResult:
    """Create the subscriber agent (or re-activate a revoked one).

    Idempotent on `stripe_customer_id`: if the agent already exists and
    is active, returns the existing name with `token=None`. If the agent
    exists but was revoked (prior cancellation), rotates the token and
    activates it again — but returns the new token so the caller can
    email it. Matches the expected Stripe flow where
    `checkout.session.completed` for a returning customer restores access.
    """
    name = agent_name_for_customer(stripe_customer_id)

    existing = await store.get_by_name(name)
    if existing is not None:
        # Already active. DO NOT mint a new token — the subscriber still
        # has the original from their first signup. Log for audit.
        log_event(
            logger,
            logging.INFO,
            "billing.stripe.provision_idempotent",
            f"Stripe webhook re-fired for already-active subscriber {name}",
            data={
                "agent_name": name,
                "stripe_customer_id": stripe_customer_id,
            },
        )
        await store.audit(
            event="billing.stripe.provision_idempotent",
            agent_name=name,
            actor=actor,
            details={"stripe_customer_id": stripe_customer_id},
        )
        return ProvisionResult(agent_name=name, token=None, created=False)

    # Fresh agent (either never existed, or was revoked — create() will
    # raise DuplicateAgentError on a soft-deleted record, so we handle
    # that with a targeted reactivation path).
    token = generate_token(name)
    token_hash_value = hash_token(token)

    try:
        await store.create(
            name=name,
            token_hash=token_hash_value,
            scopes=[SUBSCRIBER_SCOPE],
            tier=SUBSCRIBER_TIER,
            created_by=actor,
            contact_email=contact_email,
        )
        created = True
    except Exception as exc:
        # Most likely a soft-revoked record with the same name. Rotate
        # the token + clear the revocation. The token_hash update +
        # explicit UPDATE to clear revoked_at is the reactivation path.
        log_event(
            logger,
            logging.INFO,
            "billing.stripe.reactivate_subscriber",
            f"Reactivating soft-revoked agent {name}: {exc}",
            data={"agent_name": name, "exception": type(exc).__name__},
        )
        await _reactivate_revoked_agent(
            store, name=name, token_hash_value=token_hash_value
        )
        created = False

    await store.audit(
        event="billing.stripe.provision",
        agent_name=name,
        actor=actor,
        details={
            "stripe_customer_id": stripe_customer_id,
            "contact_email": contact_email,
            "scope": SUBSCRIBER_SCOPE,
            "tier": SUBSCRIBER_TIER,
            "created_new": created,
        },
    )
    log_event(
        logger,
        logging.INFO,
        "billing.stripe.provision",
        f"Provisioned subscriber {name} (created={created})",
        data={
            "agent_name": name,
            "stripe_customer_id": stripe_customer_id,
            "scope": SUBSCRIBER_SCOPE,
            "tier": SUBSCRIBER_TIER,
            "created_new": created,
        },
    )
    return ProvisionResult(agent_name=name, token=token, created=created)


async def revoke_subscriber(
    store: "IdentityStore",
    *,
    stripe_customer_id: str,
    reason: str = "stripe_subscription_deleted",
    actor: str = "stripe_webhook",
) -> bool:
    """Revoke the subscriber's scope on `customer.subscription.deleted`.

    Per spec §6: keeps the identity record (revoked_at=NOW) for audit
    trail, does NOT delete. If the caller re-subscribes later,
    `provision_subscriber` handles the reactivation path.

    Returns True if a revocation happened, False if the agent wasn't found
    (idempotent-safe: duplicate webhook deliveries are no-ops).
    """
    name = agent_name_for_customer(stripe_customer_id)
    existing = await store.get_by_name(name)
    if existing is None:
        log_event(
            logger,
            logging.INFO,
            "billing.stripe.revoke_noop",
            f"Subscription.deleted for unknown/already-revoked agent {name}",
            data={"agent_name": name, "stripe_customer_id": stripe_customer_id},
        )
        return False

    await store.revoke(name=name, reason=reason, actor=actor)
    await store.audit(
        event="billing.stripe.revoke",
        agent_name=name,
        actor=actor,
        details={"stripe_customer_id": stripe_customer_id, "reason": reason},
    )
    log_event(
        logger,
        logging.INFO,
        "billing.stripe.revoke",
        f"Revoked subscriber {name} (reason={reason})",
        data={
            "agent_name": name,
            "stripe_customer_id": stripe_customer_id,
            "reason": reason,
        },
    )
    return True


async def _reactivate_revoked_agent(
    store: "IdentityStore",
    *,
    name: str,
    token_hash_value: str,
) -> None:
    """Clear the revoked_at timestamp and rotate the token hash in a
    single atomic path. Used by `provision_subscriber` when a create()
    collides with a soft-deleted record.

    Reaches into the pool because IdentityStore doesn't expose an
    explicit "reactivate" primitive; kept inside this module so the
    identity API stays narrow.
    """
    async with store._pool.acquire() as conn:  # pylint: disable=protected-access
        await conn.execute(
            """
            UPDATE identity.agents
            SET revoked_at = NULL,
                revocation_reason = NULL,
                token_hash = $2
            WHERE name = $1
            """,
            name,
            token_hash_value,
        )
