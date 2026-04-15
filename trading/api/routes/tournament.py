from __future__ import annotations
from typing import TYPE_CHECKING
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from api.auth import verify_api_key
from api.identity.dependencies import require_scope

if TYPE_CHECKING:
    from tournament.engine import TournamentEngine


class OverrideRequest(BaseModel):
    agent_name: str
    action: str  # "promote" or "demote"
    by: str = "api"


def create_tournament_router(engine: TournamentEngine) -> APIRouter:
    router = APIRouter(prefix="/tournament", tags=["tournament"])

    @router.post("/override", dependencies=[Depends(require_scope("admin"))])
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

    @router.get("/elo", dependencies=[Depends(verify_api_key)])
    async def get_elo_ratings():
        """Get ELO ratings for all agents. Used by consensus.py AgentWeightProvider."""
        elo_ratings = await engine.get_elo_ratings()
        return {"elo_ratings": elo_ratings, "count": len(elo_ratings)}

    @router.get("/elo/{agent_name}", dependencies=[Depends(verify_api_key)])
    async def get_agent_elo(agent_name: str):
        """Get ELO rating and history for a specific agent."""
        current_elo = await engine._store.get_elo(agent_name)
        history = await engine._store.get_elo_history(agent_name, limit=10)
        return {
            "agent_name": agent_name,
            "elo_rating": current_elo,
            "history": history,
        }

    @router.get("/rankings", dependencies=[Depends(verify_api_key)])
    async def get_rankings():
        """Get current tournament rankings sorted by Sharpe ratio."""
        rankings = await engine.compute_rankings()
        return {"rankings": rankings, "count": len(rankings)}

    @router.post("/run", dependencies=[Depends(require_scope("admin"))])
    async def run_tournament():
        """Run complete tournament cycle: evaluate, rank, update ELO."""
        results = await engine.run_tournament()
        return results

    return router
