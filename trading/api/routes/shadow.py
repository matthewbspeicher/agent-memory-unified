"""Read-only shadow execution API routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.auth import verify_api_key
from api.identity.dependencies import require_scope
from storage.shadow import ShadowExecutionStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/shadow",
    tags=["shadow"],
    dependencies=[Depends(verify_api_key)],
)


def _get_store(request: Request) -> ShadowExecutionStore:
    store = getattr(request.app.state, "shadow_execution_store", None)
    if store is None:
        raise HTTPException(
            status_code=501, detail="Shadow execution store not configured"
        )
    return store


@router.get("/executions")
async def list_shadow_executions(
    agent_name: str | None = None,
    symbol: str | None = None,
    decision_status: str | None = None,
    resolution_status: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    store: ShadowExecutionStore = Depends(_get_store),
):
    return await store.list(
        agent_name=agent_name,
        symbol=symbol,
        decision_status=decision_status,
        resolution_status=resolution_status,
        limit=limit,
    )


@router.get("/executions/{record_id}")
async def get_shadow_execution(
    record_id: str,
    store: ShadowExecutionStore = Depends(_get_store),
):
    record = await store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Shadow execution not found")
    return record


@router.get("/summary")
async def get_shadow_summary(store: ShadowExecutionStore = Depends(_get_store)):
    return await store.summary_by_agent()


@router.get("/agents/{agent_name}/summary")
async def get_agent_shadow_summary(
    agent_name: str,
    store: ShadowExecutionStore = Depends(_get_store),
    request: Request = None,
):
    """Get shadow execution summary for a specific agent."""
    stats = await store.summary_for_agent(agent_name)
    if stats is None:
        raise HTTPException(
            status_code=404,
            detail=f"No shadow execution data for agent '{agent_name}'",
        )

    # Try to get agent config for promotion criteria
    agent_store = getattr(request.app.state, "agent_store", None)
    promotion_criteria = None
    eligible_for_promotion = None

    if agent_store:
        try:
            agent = await agent_store.get(agent_name)
            if agent:
                promotion_criteria = agent.get("promotion_criteria")
                if promotion_criteria:
                    eligible_for_promotion = stats[
                        "total_count"
                    ] >= promotion_criteria.get("min_cycles", 0) and stats[
                        "win_rate"
                    ] >= promotion_criteria.get("min_win_rate", 0)
        except Exception:
            pass  # Agent store may not be available

    return {
        "agent_name": agent_name,
        "stats": stats,
        "promotion_criteria": promotion_criteria,
        "eligible_for_promotion": eligible_for_promotion,
    }


@router.post(
    "/agents/{agent_name}/promote",
    dependencies=[Depends(require_scope("control:agents"))],
)
async def promote_agent(
    agent_name: str,
    request: Request,
    promoted_by: str = "manual",
    rationale: str | None = None,
):
    agent_store = getattr(request.app.state, "agent_store", None)
    if agent_store is None:
        raise HTTPException(status_code=501, detail="Agent store not configured")

    agent = await agent_store.get(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    if not agent.get("shadow_mode"):
        raise HTTPException(status_code=400, detail="Agent is not in shadow mode")

    # Build promotion entry
    promotion_entry: dict = {
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "promoted_by": promoted_by,
        "rationale": rationale,
    }

    # Get shadow stats if available
    shadow_store = getattr(request.app.state, "shadow_execution_store", None)
    if shadow_store:
        try:
            stats = await shadow_store.summary_for_agent(agent_name)
            if stats:
                promotion_entry["shadow_stats"] = {
                    "total_count": stats.get("total_count", 0),
                    "win_rate": stats.get("win_rate", 0),
                    "total_pnl": stats.get("total_pnl", 0),
                }
        except Exception:
            pass

    # Update agent's shadow_mode in runner if available
    runner = getattr(request.app.state, "agent_runner", None)
    if runner:
        await runner.update_agent_shadow_mode(agent_name, shadow_mode=False)

    # Persist promotion to agent_registry (update shadow_mode + creation_context)
    if agent_store:
        try:
            await agent_store.update(
                agent_name,
                {
                    "shadow_mode": 0,
                    "creation_context": {
                        **(agent.get("creation_context") or {}),
                        "promoted_at": promotion_entry["promoted_at"],
                        "promoted_by": promoted_by,
                        "promotion_rationale": rationale,
                    },
                },
            )
        except Exception as exc:
            logger.warning(f"Failed to persist promotion to agent_registry: {exc}")

    return {
        "name": agent_name,
        "shadow_mode": False,
        "promotion_history": [promotion_entry],
        "previous_shadow_mode": True,
    }
