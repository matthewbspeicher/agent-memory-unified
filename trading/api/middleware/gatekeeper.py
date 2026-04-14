import json
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from models.user import PlatformTier

ALPHA_FIELDS = {"whale_address", "entry_price", "take_profit", "reasoning"}

def redact_for_tier(data, tier: str):
    if tier in (PlatformTier.TRADER.value, PlatformTier.ENTERPRISE.value, PlatformTier.WHALE.value):
        return data
    
    if isinstance(data, dict):
        return {k: ("locked" if k in ALPHA_FIELDS else redact_for_tier(v, tier)) for k, v in data.items()}
    elif isinstance(data, list):
        return [redact_for_tier(item, tier) for item in data]
    return data

class GatekeeperMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response
            
        tier = PlatformTier.EXPLORER.value
        if hasattr(request.state, "user") and request.state.user:
            tier = request.state.user.tier.value if hasattr(request.state.user.tier, "value") else request.state.user.tier
            
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
            
        try:
            data = json.loads(body)
            redacted_data = redact_for_tier(data, tier)
            new_body = json.dumps(redacted_data).encode("utf-8")
            
            headers = dict(response.headers)
            headers["content-length"] = str(len(new_body))
            
            return Response(
                content=new_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type
            )
        except json.JSONDecodeError:
            headers = dict(response.headers)
            headers["content-length"] = str(len(body))
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type
            )
