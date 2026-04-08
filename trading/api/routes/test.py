from fastapi import APIRouter, Depends, HTTPException
from api.auth import verify_api_key


def create_test_router(wa_client=None, allowed_numbers: str | None = None) -> APIRouter:
    router = APIRouter(prefix="/test", tags=["test"], dependencies=[Depends(verify_api_key)])

    @router.post("/whatsapp")
    async def test_whatsapp():
        if not wa_client or not allowed_numbers:
            raise HTTPException(status_code=400, detail="WhatsApp not configured")
        to = allowed_numbers.split(",")[0].strip()
        await wa_client.send_text(
            to=to,
            body="\U0001f7e2 Smoke test passed \u2014 your trading bot is live!",
        )
        return {"sent": True, "to": to}

    return router
