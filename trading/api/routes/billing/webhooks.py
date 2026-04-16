import os
import stripe
import json
from fastapi import APIRouter, Request, HTTPException, Depends
from api.identity.store import IdentityStore
from models.user import PlatformTier
from api.auth.users import get_identity_store

router = APIRouter()


def _stripe_enabled() -> bool:
    """Feature-flag the broken Stripe webhook handler.

    The current implementation parses unsigned JSON and grants tier upgrades
    based on a `customer_email` field that any caller can spoof — anyone
    able to POST to /billing/stripe/webhooks could promote arbitrary users
    to TRADER. Until signature verification + idempotency land per the
    spec §6 (PM Arb Signal Feed v1) + the unified monetization spec,
    keep this route disabled by default.

    Set STA_STRIPE_ENABLED=true to opt in (e.g. in a test env that has
    wired stripe.Webhook.construct_event with the right secret).
    """
    return os.getenv("STA_STRIPE_ENABLED", "false").lower() in ("1", "true", "yes")


@router.post("/stripe/webhooks")
async def stripe_webhook(request: Request, store: IdentityStore = Depends(get_identity_store)):
    if not _stripe_enabled():
        # 410 Gone signals to Stripe (and to scanners) that this endpoint
        # is intentionally retired. Do NOT 404 — Stripe retries on 4xx
        # other than 410 and would flood logs.
        raise HTTPException(
            status_code=410,
            detail=(
                "Stripe webhook is disabled. The current handler does not "
                "verify Stripe signatures and is unsafe in production. "
                "Set STA_STRIPE_ENABLED=true only in environments where "
                "signature verification is wired."
            ),
        )

    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    # In a real implementation, you would verify the signature using stripe.Webhook.construct_event
    # and a secret key. For this phase, we mock the verification or use a dummy secret if testing.
    # event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    # For now, just parse the JSON from payload
    try:
        event = json.loads(payload.decode('utf-8'))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        # Upgrade User Tier to TRADER
        session = event['data']['object']
        customer_email = session.get('customer_details', {}).get('email')
        if customer_email:
            user = await store.get_user_by_email(customer_email)
            if user:
                await store.update_user_tier(user.id, PlatformTier.TRADER)
    elif event['type'] == 'customer.subscription.deleted':
        # Downgrade User Tier to EXPLORER
        pass

    return {"status": "success"}
