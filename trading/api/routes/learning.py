from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import verify_api_key
from storage.agent_registry import AgentStore
from storage.performance import PerformanceStore
from storage.pnl import TrackedPositionStore

logger = logging.getLogger(__name__)


class TrustUpdateRequest(BaseModel):
    trust_level: str


def create_learning_router(
    pnl_store: TrackedPositionStore,
    perf_store: PerformanceStore,
    agent_store: AgentStore,
) -> APIRouter:
    router = APIRouter(prefix="/api/agents", tags=["learning"], dependencies=[Depends(verify_api_key)])

    @router.get("/{name}/pnl")
    async def get_pnl(name: str, status: str = "closed") -> list:
        if status == "open":
            return await pnl_store.list_open(agent_name=name)
        return await pnl_store.list_closed(agent_name=name)

    @router.get("/{name}/performance")
    async def get_performance(name: str) -> list:
        snapshots = await perf_store.get_history(name)
        return [s.model_dump() for s in snapshots]

    @router.get("/{name}/performance/summary")
    async def get_performance_summary(name: str) -> dict:
        snapshot = await perf_store.get_latest(name)
        if snapshot is None:
            return {"message": "No performance data available"}
        return snapshot.model_dump()

    @router.put("/{name}/trust")
    async def put_trust(name: str, body: TrustUpdateRequest) -> dict:
        current = await agent_store.get(name)
        old_level = current.get("trust_level", "none") if current else "none"
        await agent_store.update(name, trust_level=body.trust_level)
        await agent_store.log_trust_change(name, old_level, body.trust_level, "rest_api")
        logger.info("Trust level for %s changed from %s to %s by rest_api", name, old_level, body.trust_level)
        return {"agent": name, "trust_level": body.trust_level}

    @router.get("/{name}/trust/history")
    async def get_trust_history(name: str) -> list:
        return await agent_store.get_trust_history(name)

    @router.delete("/{name}/overrides")
    async def delete_overrides(name: str) -> dict:
        # Reset runtime overrides for this agent
        await agent_store.update(name, runtime_overrides={})
        return {"agent": name, "status": "overrides_deleted"}

    return router
