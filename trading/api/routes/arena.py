from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from api.auth import verify_api_key
from competition.arena_rewards import (
    award_arena_completion_rewards,
    get_arena_achievement_checks,
)

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


class ClaimRewardsRequest(BaseModel):
    session_id: str
    asset: str = "BTC"


class ClaimRewardsResponse(BaseModel):
    xp_awarded: int
    bonus_xp: int
    total_xp: int
    achievements: list[dict]


@router.post("/sessions/claim-rewards", response_model=ClaimRewardsResponse)
async def claim_session_rewards(
    body: ClaimRewardsRequest,
    request: Request,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)

    session = await store.get_arena_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session["status"] != "completed":
        raise HTTPException(
            status_code=400, detail="Session must be completed to claim rewards"
        )

    challenge = await store.get_arena_challenge(session["challenge_id"])
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    rewards = await award_arena_completion_rewards(
        store=store,
        competitor_id=session["agent_id"],
        asset=body.asset,
        session_data=session,
        challenge_data=challenge,
    )

    achievements = get_arena_achievement_checks(
        session_data=session,
        challenge_data=challenge,
        competitor_stats=None,
    )

    return ClaimRewardsResponse(
        xp_awarded=rewards["xp_awarded"],
        bonus_xp=rewards["bonus_xp"],
        total_xp=rewards["total_xp"],
        achievements=achievements,
    )


class PlaceBetRequest(BaseModel):
    session_id: str
    predicted_winner: str
    amount: int


class BetResponse(BaseModel):
    id: str
    session_id: str
    better_id: str
    predicted_winner: str
    amount: int
    potential_payout: int
    status: str


class BettingPoolResponse(BaseModel):
    session_id: str
    total_pool: int
    player_a_pool: int
    player_b_pool: int
    player_a_odds: float
    player_b_odds: float
    status: str


class BetLeaderboardEntry(BaseModel):
    user_id: str
    total_profit: int
    total_bets: int
    wins: int


@router.get("/bets/leaderboard", response_model=list[BetLeaderboardEntry])
async def get_bet_leaderboard(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    leaderboard = await store.get_arena_betting_leaderboard(limit=limit)
    return [BetLeaderboardEntry(**e) for e in leaderboard]


@router.get("/sessions/{session_id}/pool", response_model=BettingPoolResponse)

async def place_arena_bet(
    body: PlaceBetRequest,
    request: Request,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)

    session = await store.get_arena_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session["status"] != "in_progress":
        raise HTTPException(
            status_code=400, detail="Can only bet on in-progress sessions"
        )

    try:
        bet = await store.place_arena_bet(
            session_id=body.session_id,
            better_id="user",
            predicted_winner=body.predicted_winner,
            amount=body.amount,
        )
        return BetResponse(
            id=bet["id"],
            session_id=body.session_id,
            better_id=bet["better_id"],
            predicted_winner=bet["predicted_winner"],
            amount=bet["amount"],
            potential_payout=bet["potential_payout"],
            status=bet["status"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions/{session_id}/pool", response_model=BettingPoolResponse)
async def get_arena_betting_pool(
    session_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)

    session = await store.get_arena_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    pool = await store.get_arena_betting_pool(session_id)
    return BettingPoolResponse(
        session_id=session_id,
        total_pool=pool.get("total_pool", 0),
        player_a_pool=pool.get("player_a_pool", 0),
        player_b_pool=pool.get("player_b_pool", 0),
        player_a_odds=pool.get("player_a_odds", 0.5),
        player_b_odds=pool.get("player_b_odds", 0.5),
        status=pool.get("status", "open"),
    )
