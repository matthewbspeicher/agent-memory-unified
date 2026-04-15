"""Strategy health status and override API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth import verify_api_key
from api.identity.dependencies import require_scope
from storage.strategy_health import StrategyHealthStore

router = APIRouter(prefix="/analytics/strategy-health", tags=["strategy-health"])


def _get_store(request: Request) -> StrategyHealthStore:
    return StrategyHealthStore(request.app.state.db)


def _get_health_engine(request: Request):
    """Return the StrategyHealthEngine from app state, or None if not configured."""
    return getattr(request.app.state, "health_engine", None)


def _get_runner(request: Request):
    """Return the AgentRunner from app state, or None if not configured."""
    return getattr(request.app.state, "agent_runner", None)


# ------------------------------------------------------------------
# Request/Response schemas
# ------------------------------------------------------------------


class OverrideRequest(BaseModel):
    status: str
    reason: str = "operator override"


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.get("")
async def list_all_health(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Return health status for all strategies."""
    store = _get_store(request)
    rows = await store.get_all_statuses()
    return rows


@router.get("/{agent_name}")
async def get_agent_health(
    request: Request,
    agent_name: str,
    _: str = Depends(verify_api_key),
):
    """Return current health status and recent events for a single agent."""
    store = _get_store(request)
    status = await store.get_status(agent_name)
    events = await store.get_events(agent_name, limit=20)
    return {
        "agent_name": agent_name,
        "status": status,
        "recent_events": events,
    }


@router.post(
    "/{agent_name}/override",
    dependencies=[Depends(require_scope("control:agents"))],
)
async def override_agent_health(
    request: Request,
    agent_name: str,
    body: OverrideRequest,
):
    """Apply an operator override to a strategy's health status."""
    from learning.strategy_health import StrategyHealthStatus

    # Validate the requested status value
    try:
        StrategyHealthStatus(body.status)
    except ValueError:
        valid = [s.value for s in StrategyHealthStatus]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{body.status}'. Must be one of: {valid}",
        )

    store = _get_store(request)
    await store.set_override(
        agent_name=agent_name,
        status=body.status,
        actor="operator",
        reason=body.reason,
    )
    return {
        "agent_name": agent_name,
        "status": body.status,
        "reason": body.reason,
        "actor": "operator",
    }


@router.post(
    "/recompute",
    dependencies=[Depends(require_scope("control:agents"))],
)
async def recompute_all_health(
    request: Request,
):
    """Admin: trigger a full health recompute for all known agents.

    Recomputes health for all agents registered with the runner, or all agents
    that already have a health record if the runner is not available.
    """
    health_engine = _get_health_engine(request)
    if health_engine is None:
        raise HTTPException(status_code=503, detail="Health engine not configured")

    # Collect agent names: prefer runner (live list), fall back to stored statuses
    agent_names: list[str] = []
    runner = _get_runner(request)
    if runner is not None:
        try:
            statuses = runner.get_all_statuses()
            agent_names = list(statuses.keys())
        except Exception:
            pass

    if not agent_names:
        store = _get_store(request)
        rows = await store.get_all_statuses()
        agent_names = [r["agent_name"] for r in rows]

    if not agent_names:
        return {"recomputed": 0, "results": {}}

    results = await health_engine.recompute_all(agent_names)
    return {"recomputed": len(results), "results": results}
