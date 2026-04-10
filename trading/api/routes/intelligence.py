from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from api.auth import verify_api_key

router = APIRouter(prefix="/intelligence", tags=["intelligence"], dependencies=[Depends(verify_api_key)])

@router.get("/status")
async def get_intel_status(request: Request):
    """Get the current status and metrics of the Intelligence Layer."""
    intel_layer = getattr(request.app.state, "intelligence_layer", None)
    if not intel_layer:
        return {"enabled": False, "status": "not_initialized"}
    
    return intel_layer.get_status()
