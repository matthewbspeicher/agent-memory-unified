import stripe
import json
from fastapi import APIRouter, Request, HTTPException, Depends
from trading.api.identity.store import IdentityStore
from trading.models.user import PlatformTier
from api.auth.users import get_identity_store

router = APIRouter()

@router.post("/stripe/webhooks")
async def stripe_webhook(request: Request, store: IdentityStore = Depends(get_identity_store)):
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
