from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from api.deps import get_agent_runner
from api.auth import verify_api_key
from agents.runner import AgentRunner
from reports.digest import DigestGenerator
from storage.performance import PerformanceSnapshot, PerformanceStore

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/digest", response_class=HTMLResponse)
async def get_daily_digest(request: Request, _: str = Depends(verify_api_key)):
    db = request.app.state.db
    generator = DigestGenerator(db)
    return await generator.generate_daily_digest()

@router.get("/agents/{agent_name}/performance", response_model=list[PerformanceSnapshot])
async def get_agent_performance(
    request: Request,
    agent_name: str,
    limit: int = 100,
    runner: AgentRunner = Depends(get_agent_runner),
    _: str = Depends(verify_api_key),
):
    if not runner.get_agent_info(agent_name):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    db = request.app.state.db
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")
    store = PerformanceStore(db)
    return await store.get_history(agent_name, limit=limit)
