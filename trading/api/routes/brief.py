from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import verify_api_key

router = APIRouter(tags=["Brief"], dependencies=[Depends(verify_api_key)])


@router.get("/brief")
async def get_brief(request: Request):
    """Return today's morning brief (generates on first call)."""
    brief_gen = getattr(request.app.state, "brief_generator", None)
    if not brief_gen:
        raise HTTPException(status_code=501, detail="Morning Brief not configured")
    return await brief_gen.get_or_generate()


@router.get("/brief/history")
async def get_brief_history(request: Request, days: int = 7):
    """Return last N daily briefs."""
    brief_gen = getattr(request.app.state, "brief_generator", None)
    if not brief_gen:
        raise HTTPException(status_code=501, detail="Morning Brief not configured")
    briefs = await brief_gen.get_history(days=days)
    return {"briefs": briefs}
