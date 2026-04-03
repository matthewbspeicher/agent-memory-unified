"""Execution quality API routes."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import verify_api_key

router = APIRouter(tags=["Execution Quality"], dependencies=[Depends(verify_api_key)])


@router.get("/execution/quality")
async def get_execution_quality(
    request: Request,
    agent_name: str | None = None,
    limit: int = 100,
):
    """
    Return execution quality (slippage) data.

    Optionally filter by agent_name. Returns per-agent averages and
    edge-erosion status.
    """
    exec_store = getattr(request.app.state, "execution_store", None)
    exec_tracker = getattr(request.app.state, "execution_tracker", None)

    if not exec_store and not exec_tracker:
        raise HTTPException(status_code=501, detail="Execution tracker not configured")

    # Try to get from persistent store first
    if exec_store:
        try:
            stats = await exec_store.get_average_slippage(agent_name)
            return stats
        except Exception:
            pass

    # Fallback: use in-memory tracker
    if exec_tracker:
        if agent_name:
            fills = exec_tracker.get_fills(agent_name)
            return {
                "agent_name": agent_name,
                "fill_count": len(fills),
                "avg_slippage_bps": exec_tracker.average_slippage_bps(agent_name),
            }
        else:
            return {
                "agents": [
                    {
                        "agent_name": name,
                        "fill_count": len(fills),
                        "avg_slippage_bps": round(
                            sum(f.slippage_bps for f in fills) / len(fills), 2
                        ) if fills else 0.0,
                    }
                    for name, fills in exec_tracker._fills.items()
                ]
            }

    raise HTTPException(status_code=404, detail="No execution data available")


@router.get("/execution/quality/{agent_name}/fills")
async def get_agent_fills(
    agent_name: str,
    request: Request,
    limit: int = 50,
):
    """Return raw fill records for a specific agent."""
    exec_store = getattr(request.app.state, "execution_store", None)
    if not exec_store:
        raise HTTPException(status_code=501, detail="Execution store not configured")

    fills = await exec_store.get_fills_for_agent(agent_name, limit=limit)
    return {"agent_name": agent_name, "fills": fills, "count": len(fills)}
