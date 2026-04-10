# trading/api/routes/arena.py
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from api.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engine/v1/arena", tags=["arena"])


def _get_store(request: Request):
    store = getattr(request.app.state, "competition_store", None)
    if store is None:
        raise HTTPException(
            status_code=503, detail="Competition system not initialized"
        )
    return store


class ArenaGymResponse(BaseModel):
    id: str
    name: str
    description: str
    room_type: str
    difficulty: int
    xp_reward: float
    max_turns: int
    icon: str
    challenge_count: int


class ArenaChallengeResponse(BaseModel):
    id: str
    gym_id: str
    name: str
    description: str
    difficulty: int
    room_type: str
    initial_state: dict
    tools: list[str]
    max_turns: int
    xp_reward: float
    flag_hint: str | None = None


class StartSessionRequest(BaseModel):
    challenge_id: str
    agent_id: str


class StartSessionResponse(BaseModel):
    id: str
    challenge_id: str
    agent_id: str
    current_state: str
    inventory: list[str]
    turn_count: int
    score: float
    status: str


class ExecuteTurnRequest(BaseModel):
    tool_name: str
    kwargs: dict = {}


class ExecuteTurnResponse(BaseModel):
    id: str
    turn_number: int
    tool_name: str
    tool_input: dict
    tool_output: str
    score_delta: float
    status: str


class ArenaTurnResponse(BaseModel):
    id: str
    turn_number: int
    tool_name: str
    tool_input: dict
    tool_output: str
    score_delta: float
    created_at: str


class GetSessionResponse(BaseModel):
    id: str
    challenge_id: str
    agent_id: str
    current_state: str
    inventory: list[str]
    turn_count: int
    score: float
    status: str
    created_at: str
    completed_at: str | None = None
    turns: list[ArenaTurnResponse]


@router.get("/gyms", response_model=list[ArenaGymResponse])
async def get_gyms(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Get all arena gyms with challenge counts."""
    store = _get_store(request)
    gyms = await store.get_arena_gyms()
    return [ArenaGymResponse(**g) for g in gyms]


@router.get("/challenges", response_model=list[ArenaChallengeResponse])
async def get_challenges(
    request: Request,
    _: str = Depends(verify_api_key),
    gym_id: str | None = Query(None, description="Filter by gym ID"),
):
    """Get challenges, optionally filtered by gym."""
    store = _get_store(request)
    challenges = await store.get_arena_challenges(gym_id=gym_id)
    return [ArenaChallengeResponse(**c) for c in challenges]


@router.post("/sessions", response_model=StartSessionResponse)
async def start_session(
    body: StartSessionRequest,
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Start a new arena session for an agent."""
    store = _get_store(request)
    try:
        session = await store.start_arena_session(
            challenge_id=body.challenge_id,
            agent_id=body.agent_id,
        )
        return StartSessionResponse(**session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sessions/{session_id}/turns", response_model=ExecuteTurnResponse)
async def execute_turn(
    session_id: str,
    body: ExecuteTurnRequest,
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Execute a tool in an arena session."""
    store = _get_store(request)
    try:
        result = await store.execute_arena_turn(
            session_id=session_id,
            tool_name=body.tool_name,
            kwargs=body.kwargs,
        )
        return ExecuteTurnResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sessions/{session_id}", response_model=GetSessionResponse)
async def get_session(
    session_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Get session details with turn history."""
    store = _get_store(request)
    session = await store.get_arena_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    turns = [
        ArenaTurnResponse(
            id=t["id"],
            turn_number=t["turn_number"],
            tool_name=t["tool_name"],
            tool_input=json.loads(t["tool_input"])
            if isinstance(t["tool_input"], str)
            else t["tool_input"],
            tool_output=t["tool_output"],
            score_delta=t["score_delta"],
            created_at=t["created_at"].isoformat()
            if hasattr(t["created_at"], "isoformat")
            else t["created_at"],
        )
        for t in session.get("turns", [])
    ]

    inventory = (
        json.loads(session.get("inventory", "[]"))
        if isinstance(session.get("inventory"), str)
        else session.get("inventory", [])
    )

    return GetSessionResponse(
        id=session["id"],
        challenge_id=session["challenge_id"],
        agent_id=session["agent_id"],
        current_state=session["current_state"],
        inventory=inventory,
        turn_count=session["turn_count"],
        score=session["score"],
        status=session["status"],
        created_at=session["created_at"].isoformat()
        if hasattr(session["created_at"], "isoformat")
        else session["created_at"],
        completed_at=session.get("completed_at").isoformat()
        if session.get("completed_at") and hasattr(session["completed_at"], "isoformat")
        else session.get("completed_at"),
        turns=turns,
    )
