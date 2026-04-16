"""Stripe webhook handler for the PM Arb Signal Feed paid tier.

Spec §6 (docs/superpowers/specs/2026-04-15-arb-signal-feed-design.md):

  `checkout.session.completed`  → provision identity-store agent
                                  (name=feed_sub_<customer_id>,
                                   scope=read:feeds.arb, tier=feed_sub),
                                  email API key to the customer
  `customer.subscription.updated` → no-op for v1 (placeholder for future
                                    plan / quantity changes)
  `customer.subscription.deleted` → revoke the subscriber agent; keep
                                    the record for audit trail

Three non-negotiables enforced here:
  1. Signature verification. Stripe signs every request with the webhook
     secret. We verify *before* any side effect.
  2. Idempotency. Stripe retries on 5xx and network failures; the same
     event_id can be delivered multiple times. The stripe_processed_events
     table (PK on event_id) gates double-provisioning.
  3. Feature flag. STA_STRIPE_ENABLED=false returns 410 Gone — so Stripe
     stops retrying and logs stay clean — until compliance clears paid
     launch.

The previous revision parsed unsigned JSON and upgraded users by email
(spoofable by anyone who could POST). Fully rewritten here; tests cover
the three failure modes plus the happy path.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api.identity.store import IdentityStore
from billing import stripe_client
from billing.subscriber_provisioning import (
    provision_subscriber,
    revoke_subscriber,
)
from utils.logging import log_event

logger = logging.getLogger(__name__)

router = APIRouter()


# Event types we handle. Anything else is acknowledged (200) but no-op'd
# so Stripe doesn't retry them. Spec §6 + Stripe best practice: return
# 200 for known-unhandled event types, 4xx for malformed, 5xx for
# transient errors we want retried.
HANDLED_EVENT_TYPES = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }
)


async def _get_identity_store(request: Request) -> IdentityStore:
    """Resolve the IdentityStore from app.state. Depends-on-Request over
    the prior module-level get_identity_store so tests can override via
    FastAPI's dependency_overrides and production gets the real store."""
    store = getattr(request.app.state, "identity_store", None)
    if store is None:
        raise HTTPException(
            status_code=500,
            detail="IdentityStore not configured on app.state",
        )
    return store


# ---------------------------------------------------------------------------
# Idempotency table (stripe_processed_events) — tiny helper layer
# ---------------------------------------------------------------------------


async def _already_processed(request: Request, event_id: str) -> bool:
    """Check the stripe_processed_events PK for this event. True = skip.

    The table schema (spec §4.2 + init_db_postgres): event_id PK,
    event_type, processed_at, result. We only need the PK lookup here;
    insertion happens after successful processing.
    """
    db = request.app.state.db
    sql = "SELECT 1 FROM stripe_processed_events WHERE event_id = ?"
    try:
        if hasattr(db, "fetchone"):
            row = await db.fetchone(sql, (event_id,))
        else:
            cursor = await db.execute(sql, (event_id,))
            row = await cursor.fetchone()
        return row is not None
    except Exception as exc:
        # DB hiccup — safer to assume NOT processed (risk double-processing
        # over lost-subscription). Provisioning itself is idempotent
        # (subscriber_provisioning.provision_subscriber) so the downside
        # is bounded.
        log_event(
            logger,
            logging.WARNING,
            "error",
            f"stripe_processed_events lookup failed: {exc}",
            data={"component": "billing.stripe", "event_id": event_id},
        )
        return False


async def _mark_processed(
    request: Request, event_id: str, event_type: str, result: str
) -> None:
    """Insert (event_id, event_type, result) with ON CONFLICT DO NOTHING.
    Called only after the event's side effects complete successfully."""
    db = request.app.state.db
    sql = (
        "INSERT OR IGNORE INTO stripe_processed_events "
        "(event_id, event_type, result) VALUES (?, ?, ?)"
    )
    try:
        await db.execute(sql, (event_id, event_type, result))
        await db.commit()
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "error",
            f"stripe_processed_events insert failed: {exc}",
            data={
                "component": "billing.stripe",
                "event_id": event_id,
                "event_type": event_type,
            },
        )


# ---------------------------------------------------------------------------
# Event handlers — keep each one tiny, delegate to subscriber_provisioning
# ---------------------------------------------------------------------------


async def _handle_checkout_completed(
    event: dict[str, Any], store: IdentityStore
) -> str:
    """On checkout.session.completed: provision the subscriber agent.

    Returns a short status string persisted to stripe_processed_events.result
    so the audit trail records what happened per event.
    """
    session = event["data"]["object"]
    customer_id = session.get("customer")
    if not customer_id:
        # Stripe should always populate this for subscription mode. Log
        # and no-op rather than crash the handler.
        log_event(
            logger,
            logging.WARNING,
            "error",
            "checkout.session.completed without customer id",
            data={
                "component": "billing.stripe",
                "event_id": event.get("id"),
            },
        )
        return "skipped_no_customer"

    email = None
    details = session.get("customer_details") or {}
    email = details.get("email") or session.get("customer_email")

    result = await provision_subscriber(
        store,
        stripe_customer_id=customer_id,
        contact_email=email,
    )
    # Delivering the minted token (emailing the API key) is a separate
    # concern. For v1 we log-structured-only so the operator can manually
    # relay the token until an email integration lands. This is the
    # intentional gap noted in spec §10 week 2: "DM 5 design-partner
    # candidates" — human-in-the-loop for the first cohort.
    if result.token:
        log_event(
            logger,
            logging.INFO,
            "billing.stripe.token_issued",
            f"New API token for {result.agent_name} — relay to {email}",
            data={
                "agent_name": result.agent_name,
                "customer_email": email,
                "token_redacted": result.token[:8] + "…"
                if result.token
                else None,
                # FULL token intentionally excluded from structured log
                # data. Operator pulls it from the audit trail by
                # agent-name lookup + token-rotation API when ready to
                # send. Until the email integration lands, a full-token
                # leak in Cloudflare/Datadog logs is the risk to avoid.
            },
        )
    return "provisioned_new" if result.created else "already_active"


async def _handle_subscription_deleted(
    event: dict[str, Any], store: IdentityStore
) -> str:
    """On customer.subscription.deleted: revoke the subscriber agent.

    Idempotent — duplicate deliveries are no-ops. Keeps the identity
    record (revoked_at=NOW) for audit trail per spec §6.
    """
    sub = event["data"]["object"]
    customer_id = sub.get("customer")
    if not customer_id:
        return "skipped_no_customer"
    revoked = await revoke_subscriber(
        store,
        stripe_customer_id=customer_id,
        reason=f"stripe_event:{event.get('id', 'unknown')}",
    )
    return "revoked" if revoked else "revoked_noop"


async def _handle_subscription_updated(event: dict[str, Any]) -> str:
    """Placeholder for plan / quantity / status changes. No-op in v1 —
    single tier, single price, so there's nothing to reconcile here
    until we add tiered pricing. Log the event for the audit trail."""
    sub = event["data"]["object"]
    log_event(
        logger,
        logging.INFO,
        "billing.stripe.subscription_updated",
        f"subscription.updated no-op for customer {sub.get('customer')}",
        data={
            "component": "billing.stripe",
            "event_id": event.get("id"),
            "customer_id": sub.get("customer"),
            "status": sub.get("status"),
        },
    )
    return "acknowledged_noop"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/stripe/webhooks")
async def stripe_webhook(
    request: Request,
    store: IdentityStore = Depends(_get_identity_store),
) -> Response:
    """Receive Stripe webhook events.

    Response codes:
      410 — feature flag off
      400 — bad signature / malformed body
      200 — event received (processed, idempotent-skipped, or acknowledged
            no-op for a known-unhandled type)
      5xx — transient error; Stripe retries per its default backoff
    """
    if not stripe_client.is_enabled():
        raise HTTPException(
            status_code=410,
            detail=(
                "Stripe webhook disabled. Set STA_STRIPE_ENABLED=true to "
                "enable (requires webhook-secret, price-id, and secret-key "
                "env vars configured per billing/stripe_client.py)."
            ),
        )

    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe_client.verify_and_parse_event(payload, sig_header)
    except stripe_client.StripeSignatureInvalidError as exc:
        log_event(
            logger,
            logging.WARNING,
            "billing.stripe.bad_signature",
            f"rejected Stripe webhook with invalid signature: {exc}",
            data={"component": "billing.stripe"},
        )
        raise HTTPException(status_code=400, detail="invalid signature") from exc
    except stripe_client.StripeDisabledError as exc:
        # Race between is_enabled() and verify_and_parse_event — only
        # possible if the flag flipped mid-request. Surface as 503 so
        # Stripe retries after the config settles.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    event_id = event.get("id") or ""
    event_type = event.get("type") or ""

    if not event_id:
        # Well-formed Stripe events always have an id; a missing id
        # points at a malformed payload slipping past verify.
        raise HTTPException(status_code=400, detail="event missing id")

    if await _already_processed(request, event_id):
        log_event(
            logger,
            logging.INFO,
            "billing.stripe.idempotent_skip",
            f"duplicate webhook delivery: {event_id}",
            data={
                "component": "billing.stripe",
                "event_id": event_id,
                "event_type": event_type,
            },
        )
        return Response(status_code=200, content='{"status":"duplicate"}',
                        media_type="application/json")

    if event_type not in HANDLED_EVENT_TYPES:
        # Record + 200 so Stripe doesn't retry unknown types.
        await _mark_processed(request, event_id, event_type, "unhandled")
        return Response(status_code=200, content='{"status":"unhandled"}',
                        media_type="application/json")

    # Dispatch. Each handler returns a short status string for the
    # audit trail. If one raises, we do NOT mark the event processed —
    # Stripe retries, which is the safer default than silently losing
    # a subscription.
    try:
        if event_type == "checkout.session.completed":
            result = await _handle_checkout_completed(event, store)
        elif event_type == "customer.subscription.deleted":
            result = await _handle_subscription_deleted(event, store)
        elif event_type == "customer.subscription.updated":
            result = await _handle_subscription_updated(event)
        else:
            # Reachable only if HANDLED_EVENT_TYPES grows without a
            # matching branch being added above — defensive fallback.
            result = "unhandled_dispatch_fallback"
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "error",
            f"Stripe webhook handler failed for {event_type}: {exc}",
            data={
                "component": "billing.stripe",
                "event_id": event_id,
                "event_type": event_type,
                "exception": type(exc).__name__,
            },
            exc_info=True,
        )
        # 500 -> Stripe retries with exponential backoff. Intentional:
        # better to retry than to lose a subscription.
        raise HTTPException(status_code=500, detail="handler failed") from exc

    await _mark_processed(request, event_id, event_type, result)
    return Response(
        status_code=200,
        content=f'{{"status":"ok","result":"{result}"}}',
        media_type="application/json",
    )
