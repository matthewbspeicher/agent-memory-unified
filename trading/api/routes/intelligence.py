from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

@router.get("/status")
async def get_intel_status(request: Request):
    """Get the current status and metrics of the Intelligence Layer."""
    intel_layer = getattr(request.app.state, "intelligence_layer", None)
    if not intel_layer:
        return {"enabled": False, "status": "not_initialized"}
    
    return intel_layer.get_status()
