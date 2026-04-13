from fastapi import APIRouter, HTTPException, Request
from llm.stats import get_stats_collector

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/stats")
def get_llm_stats():
    collector = get_stats_collector()
    return collector.get_all_stats()


@router.get("/stats/{provider}")
def get_provider_stats(provider: str):
    collector = get_stats_collector()
    return collector.get_provider_stats(provider)


@router.post("/stats/reset")
def reset_llm_stats():
    collector = get_stats_collector()
    collector.reset()
    return {"status": "reset"}


@router.get("/cost/status")
async def get_cost_status(request: Request):
    """Get current cost ceiling status including budget usage and breakdown."""
    ledger = getattr(request.app.state, "cost_ledger", None)
    if not ledger:
        raise HTTPException(status_code=503, detail="Cost ledger not initialized")
    return ledger.get_spend_summary()


@router.get("/cost/agent/{agent_name}")
async def get_agent_cost(agent_name: str, request: Request):
    """Get cost breakdown for a specific agent."""
    ledger = getattr(request.app.state, "cost_ledger", None)
    if not ledger:
        raise HTTPException(status_code=503, detail="Cost ledger not initialized")
    return ledger.get_agent_spend(agent_name)
