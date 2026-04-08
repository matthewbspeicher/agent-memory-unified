# trading/api/routes/competition.py
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from api.auth import verify_api_key
from api.routes.competition_schemas import (
    CompetitorDetailResponse,
    DashboardSummaryResponse,
    EloHistoryResponse,
    LeaderboardResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/competition", tags=["competition"])


def _get_store(request: Request):
    store = getattr(request.app.state, "competition_store", None)
    if store is None:
        raise HTTPException(
            status_code=503, detail="Competition system not initialized"
        )
    return store


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    response_model_exclude_none=True,
)
async def dashboard_summary(
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    store = _get_store(request)
    data = await store.get_dashboard_summary(asset=asset)
    return DashboardSummaryResponse(
        leaderboard=data.get("leaderboard", []),
        competitor_count=data.get("total_competitors", 0),
    )


@router.get(
    "/leaderboard",
    response_model=LeaderboardResponse,
    response_model_exclude_none=True,
)
async def get_leaderboard(
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
    type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    from competition.models import CompetitorType

    store = _get_store(request)
    comp_type = CompetitorType(type) if type else None
    entries = await store.get_leaderboard(
        asset=asset, comp_type=comp_type, limit=limit, offset=offset
    )
    return LeaderboardResponse(
        leaderboard=[e.model_dump() for e in entries],
        competitor_count=len(entries),
    )


@router.get(
    "/competitors/{competitor_id}",
    response_model=CompetitorDetailResponse,
    response_model_exclude_none=True,
)
async def get_competitor(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    record = await store.get_competitor(competitor_id)
    if not record:
        raise HTTPException(status_code=404, detail="Competitor not found")

    # Get ELO ratings for all assets
    ratings = {}
    for asset in ["BTC", "ETH"]:
        elo = await store.get_elo(competitor_id, asset)
        ratings[asset] = {"elo": elo}

    # Get calibration score
    calibration = await store.get_competitor_calibration(competitor_id)

    return CompetitorDetailResponse(
        id=record.id,
        type=record.type.value,
        name=record.name,
        ref_id=record.ref_id,
        status=record.status,
        metadata=record.metadata,
        ratings=ratings,
        calibration_score=calibration,
    )


@router.get(
    "/competitors/{competitor_id}/elo-history",
    response_model=EloHistoryResponse,
    response_model_exclude_none=True,
)
async def get_elo_history(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
    days: int = Query(30, ge=1, le=365),
):
    store = _get_store(request)
    history = await store.get_elo_history(competitor_id, asset=asset, days=days)
    return EloHistoryResponse(
        competitor_id=competitor_id,
        asset=asset,
        history=[
            {
                "elo": h["elo"],
                "tier": h["tier"],
                "elo_delta": h.get("elo_delta", 0),
                "recorded_at": str(h["recorded_at"]),
            }
            for h in history
        ],
    )


@router.get("/head-to-head/{competitor_a}/{competitor_b}")
async def head_to_head(
    competitor_a: str,
    competitor_b: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    """Head-to-head comparison between two competitors."""
    store = _get_store(request)
    stats = await store.get_head_to_head(competitor_a, competitor_b, asset)
    rec_a = await store.get_competitor(competitor_a)
    rec_b = await store.get_competitor(competitor_b)
    if not rec_a or not rec_b:
        raise HTTPException(404, "Competitor not found")
    return {
        "wins_a": stats.get("wins_a", 0),
        "wins_b": stats.get("wins_b", 0),
        "draws": stats.get("draws", 0),
        "total_matches": stats.get("total", 0),
        "competitor_a": rec_a,
        "competitor_b": rec_b,
    }


@router.get("/meta-learner/status")
async def meta_learner_status(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Get meta-learner status and feature importance."""
    meta = getattr(request.app.state, "competition_meta_learner", None)
    if not meta:
        return {"enabled": False, "mode": "baseline"}

    return {
        "enabled": True,
        "mode": meta.active_mode,
        "last_retrain": str(meta.meta_learner.last_retrain)
        if meta.meta_learner and meta.meta_learner.last_retrain
        else None,
        "feature_importance": meta.meta_learner.feature_importance
        if meta.meta_learner
        else {},
        "has_model": meta.meta_learner is not None
        and meta.meta_learner.model is not None,
    }


@router.get("/achievements/feed")
async def get_achievement_feed(
    request: Request,
    _: str = Depends(verify_api_key),
    limit: int = Query(20, ge=1, le=100),
):
    """Recent achievements, promotions, and events."""
    store = _get_store(request)
    try:
        events = await store.get_recent_achievements(since_id=0, limit=limit)
        # Return in reverse chronological order for REST API
        return list(reversed(events))
    except Exception:
        return []


# Track SSE connections for rate limiting
_sse_connections: set[str] = set()
_MAX_SSE_CONNECTIONS = 50


@router.get("/achievements/feed/stream")
async def achievement_feed_stream(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """SSE stream for real-time achievement updates. Auth via X-API-Key header.
    Rate limited to 50 concurrent connections.
    """
    client_id = (
        f"{request.client.host}:{id(request)}" if request.client else str(id(request))
    )

    if len(_sse_connections) >= _MAX_SSE_CONNECTIONS:
        raise HTTPException(status_code=429, detail="Too many SSE connections")

    _sse_connections.add(client_id)
    store = _get_store(request)

    async def event_generator():
        try:
            last_id = 0
            while True:
                if await request.is_disconnected():
                    break
                try:
                    events = await store.get_recent_achievements(
                        since_id=last_id, limit=10
                    )
                    for event in events:
                        last_id = event["id"]
                        yield {
                            "event": "achievement_earned",
                            "id": str(event["id"]),
                            "data": json.dumps(event),
                        }
                except Exception as e:
                    logger.warning("SSE error: %s", e)
                await asyncio.sleep(5)
        finally:
            _sse_connections.discard(client_id)

    return EventSourceResponse(event_generator())
