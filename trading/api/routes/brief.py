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


# --- Session Bias endpoints ---


@router.get("/brief/bias")
async def get_session_bias(request: Request):
    """Return today's session bias (cached or None)."""
    bias_gen = getattr(request.app.state, "session_bias_generator", None)
    if not bias_gen:
        raise HTTPException(status_code=501, detail="Session Bias not configured")
    bias = await bias_gen.get_active_bias()
    if not bias:
        return {"date": None, "bias": None, "message": "No bias generated yet today"}
    return bias.to_dict()


@router.post("/brief/bias/generate")
async def generate_session_bias(request: Request):
    """Force-generate today's session bias (re-scans watchlist)."""
    bias_gen = getattr(request.app.state, "session_bias_generator", None)
    if not bias_gen:
        raise HTTPException(status_code=501, detail="Session Bias not configured")
    report = await bias_gen.generate()
    return report.to_dict()


@router.get("/brief/rules")
async def get_trading_rules(request: Request):
    """Return current trading rules configuration."""
    rules_loader = getattr(request.app.state, "rules_loader", None)
    if not rules_loader:
        raise HTTPException(status_code=501, detail="Rules loader not configured")
    from dataclasses import asdict
    rules = rules_loader.get()
    return asdict(rules)
