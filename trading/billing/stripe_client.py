"""Thin wrapper around the stripe SDK for the PM Arb Signal Feed.

Keeps all Stripe-specific surface area in one module so:
  - The webhook handler only needs `verify_and_parse_event` + event-type helpers
  - The checkout endpoint only needs `create_checkout_session`
  - The reconciliation job only needs `list_active_subscriptions`
  - Tests can mock the thin surface without stubbing the whole `stripe` module

Config (trading/config.py fields; env vars are STA_STRIPE_*):
  STA_STRIPE_ENABLED          — master feature flag; when false every
                                callable here raises StripeDisabledError
                                so "paid flow off" is enforced at one point
  STA_STRIPE_SECRET_KEY       — `sk_test_...` / `sk_live_...`
  STA_STRIPE_WEBHOOK_SECRET   — `whsec_...` from the webhook endpoint
                                dashboard configuration
  STA_STRIPE_PRICE_ID_DEFAULT — recurring $500/mo price id
  STA_STRIPE_PRICE_ID_FOUNDING — optional $300/mo founding-member price

Spec §6 (trading/docs/superpowers/specs/2026-04-15-arb-signal-feed-design.md).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class StripeDisabledError(RuntimeError):
    """Raised when any Stripe callable runs while the feature flag is off.

    Spec §11 SLI: STA_STRIPE_ENABLED should be true 48h before paid-tier
    open or an alert fires. Until then, every attempt to hit a Stripe
    callable surfaces this error (and the webhook endpoint returns 410 by
    shortcutting before reaching the client). Fail-loud on misconfig.
    """


class StripeSignatureInvalidError(ValueError):
    """Raised when a webhook payload's Stripe-Signature header fails
    construct_event's cryptographic check. Always yields 400 at the route."""


# ---------------------------------------------------------------------------
# Config read + env flag
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """Check the feature flag without importing config.py — avoids circular
    imports in code paths (identity store, background jobs) that call into
    billing during their own initialization."""
    return os.getenv("STA_STRIPE_ENABLED", "false").lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class StripeConfig:
    """Resolved Stripe config. Pulled from env at call time so test overrides
    via monkeypatch.setenv work without module-reload gymnastics."""

    secret_key: str
    webhook_secret: str
    price_id_default: str
    price_id_founding: str | None

    @classmethod
    def from_env(cls) -> "StripeConfig":
        missing: list[str] = []
        secret = os.getenv("STA_STRIPE_SECRET_KEY", "").strip()
        if not secret:
            missing.append("STA_STRIPE_SECRET_KEY")
        webhook = os.getenv("STA_STRIPE_WEBHOOK_SECRET", "").strip()
        if not webhook:
            missing.append("STA_STRIPE_WEBHOOK_SECRET")
        price = os.getenv("STA_STRIPE_PRICE_ID_DEFAULT", "").strip()
        if not price:
            missing.append("STA_STRIPE_PRICE_ID_DEFAULT")
        founding = os.getenv("STA_STRIPE_PRICE_ID_FOUNDING", "").strip() or None
        if missing:
            raise StripeDisabledError(
                "Stripe config missing: %s. Set the env vars or keep "
                "STA_STRIPE_ENABLED=false." % ", ".join(missing)
            )
        return cls(
            secret_key=secret,
            webhook_secret=webhook,
            price_id_default=price,
            price_id_founding=founding,
        )


# ---------------------------------------------------------------------------
# Webhook: signature verification + parse
# ---------------------------------------------------------------------------


def verify_and_parse_event(payload: bytes, sig_header: str | None) -> dict[str, Any]:
    """Verify a Stripe webhook signature and return the parsed event.

    Raises StripeSignatureInvalidError on verification failure. Returns
    the decoded event dict on success — *not* a `stripe.Event` object,
    so callers aren't coupled to the stripe module's Python class shape
    (handy for tests and for the MemPalace-style future split where
    the webhook handler might live on a separate host).

    Spec §6: webhook is idempotent (caller is responsible for checking
    stripe_processed_events) and verifies the signature *before* any
    side effect.
    """
    if not is_enabled():
        raise StripeDisabledError(
            "Stripe webhook invoked while STA_STRIPE_ENABLED=false — "
            "route should have 410'd before reaching this layer"
        )
    if not sig_header:
        raise StripeSignatureInvalidError("missing Stripe-Signature header")

    import stripe  # imported lazily so `import billing.stripe_client` is cheap

    cfg = StripeConfig.from_env()
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=cfg.webhook_secret,
        )
    except stripe.error.SignatureVerificationError as exc:
        raise StripeSignatureInvalidError(str(exc)) from exc
    # `construct_event` returns a `stripe.Event` (dict-like). Cast through
    # `.to_dict_recursive()` so callers get a stable shape without holding
    # a reference to the stripe class.
    return event.to_dict_recursive()


# ---------------------------------------------------------------------------
# Checkout (admin / sales surface)
# ---------------------------------------------------------------------------


def create_checkout_session(
    *,
    customer_email: str | None = None,
    use_founding_price: bool = False,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    """Create a Stripe Checkout Session and return `{id, url}`.

    `customer_email` prefills the checkout form when provided. The founding-
    member price id is used when `use_founding_price=True` and a price id
    is configured; otherwise the default $500/mo price is used.
    """
    if not is_enabled():
        raise StripeDisabledError(
            "Checkout session requested while STA_STRIPE_ENABLED=false"
        )

    import stripe

    cfg = StripeConfig.from_env()
    stripe.api_key = cfg.secret_key

    price_id = (
        cfg.price_id_founding
        if use_founding_price and cfg.price_id_founding
        else cfg.price_id_default
    )
    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "allow_promotion_codes": True,
    }
    if customer_email:
        params["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**params)
    return {"id": session["id"], "url": session["url"]}


# ---------------------------------------------------------------------------
# Reconciliation support
# ---------------------------------------------------------------------------


def list_active_subscriptions(limit: int = 100) -> list[dict[str, Any]]:
    """Return active subscriptions for the reconciliation job to cross-
    check against identity-store state. Thin passthrough to the Stripe
    API; pagination is a later problem (spec targets single-digit active
    subs at launch)."""
    if not is_enabled():
        raise StripeDisabledError("list_active_subscriptions called while disabled")

    import stripe

    cfg = StripeConfig.from_env()
    stripe.api_key = cfg.secret_key
    resp = stripe.Subscription.list(status="active", limit=limit)
    return [s.to_dict_recursive() for s in resp.data]
