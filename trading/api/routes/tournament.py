from __future__ import annotations
from typing import TYPE_CHECKING
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from api.auth import verify_api_key

if TYPE_CHECKING:
    from tournament.engine import TournamentEngine


class OverrideRequest(BaseModel):
    agent_name: str
    action: str  # "promote" or "demote"
    by: str = "api"


def create_tournament_router(engine: TournamentEngine) -> APIRouter:
    router = APIRouter(prefix="/tournament", tags=["tournament"])

    @router.post("/override", dependencies=[Depends(verify_api_key)])
    async def override_agent(req: OverrideRequest):
        message = await engine.override(req.agent_name, req.action, by=req.by)
        return {"message": message}

    @router.get("/log", dependencies=[Depends(verify_api_key)])
    async def get_audit_log(limit: int = 50):
        rows = await engine._store.list_audit(limit=limit)
        return rows

    @router.get("/stages", dependencies=[Depends(verify_api_key)])
    async def get_stages():
        stages = await engine._store.get_all_stages()
        return stages

    return router
