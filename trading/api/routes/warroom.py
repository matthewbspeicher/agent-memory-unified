from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import verify_api_key

router = APIRouter(tags=["War Room"], dependencies=[Depends(verify_api_key)])


@router.get("/warroom")
async def get_convergences(request: Request, hours: int = 4):
    """List active convergence signals."""
    engine = getattr(request.app.state, "warroom_engine", None)
    if not engine:
        raise HTTPException(status_code=501, detail="War Room not configured")
    signals = await engine.detect_convergences(hours=hours)
    return {"signals": [s.to_dict() for s in signals]}


@router.get("/warroom/{convergence_id}/synthesis")
async def get_synthesis(convergence_id: str, request: Request, hours: int = 4):
    """Get or generate LLM synthesis for a convergence signal."""
    engine = getattr(request.app.state, "warroom_engine", None)
    if not engine:
        raise HTTPException(status_code=501, detail="War Room not configured")
    synthesis = await engine.synthesize(convergence_id, hours=hours)
    if synthesis is None:
        raise HTTPException(status_code=404, detail="Convergence signal not found")
    return {"convergence_id": convergence_id, "synthesis": synthesis}


@router.get("/warroom/timeline")
async def get_timeline(request: Request, hours: int = 24):
    """Return all recent opportunities as a timeline."""
    engine = getattr(request.app.state, "warroom_engine", None)
    if not engine:
        raise HTTPException(status_code=501, detail="War Room not configured")
    events = await engine.get_timeline(hours=hours)
    return {"events": events}
