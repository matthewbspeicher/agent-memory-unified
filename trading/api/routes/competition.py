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

    return CompetitorDetailResponse(
        id=record.id,
        type=record.type.value,
        name=record.name,
        ref_id=record.ref_id,
        status=record.status,
        metadata=record.metadata,
        ratings=ratings,
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


@router.get("/achievements/feed")
async def get_achievement_feed(
    request: Request,
    _: str = Depends(verify_api_key),
    limit: int = Query(20, ge=1, le=100),
):
    """Recent achievements, promotions, and events."""
    store = _get_store(request)
    try:
        async with store._db.execute(
            """
            SELECT a.id, a.competitor_id, a.achievement_type, a.earned_at, a.metadata,
                   c.name, c.type
            FROM achievements a
            JOIN competitors c ON c.id = a.competitor_id
            ORDER BY a.earned_at DESC
            LIMIT $1
            """,
            [limit],
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": row["id"],
                "competitor_name": row["name"],
                "competitor_type": row["type"],
                "achievement_type": row["achievement_type"],
                "earned_at": str(row["earned_at"]),
                "metadata": row.get("metadata", {}),
            }
            for row in rows
        ]
    except Exception:
        return []


@router.get("/achievements/feed/stream")
async def achievement_feed_stream(request: Request):
    """SSE stream for real-time achievement updates."""

    async def event_generator():
        last_id = 0
        while True:
            if await request.is_disconnected():
                break
            try:
                store = getattr(request.app.state, "competition_store", None)
                if store:
                    async with store._db.execute(
                        """
                        SELECT a.id, a.competitor_id, a.achievement_type, a.earned_at,
                               c.name, c.type
                        FROM achievements a
                        JOIN competitors c ON c.id = a.competitor_id
                        WHERE a.id > $1
                        ORDER BY a.earned_at ASC LIMIT 10
                        """,
                        [last_id],
                    ) as cur:
                        rows = await cur.fetchall()
                    for row in rows:
                        last_id = row["id"]
                        yield {
                            "event": "achievement_earned",
                            "id": str(row["id"]),
                            "data": json.dumps(
                                {
                                    "competitor": row["name"],
                                    "type": row["achievement_type"],
                                    "earned_at": str(row["earned_at"]),
                                }
                            ),
                        }
            except Exception as e:
                logger.warning("SSE error: %s", e)
            await asyncio.sleep(5)

    return EventSourceResponse(event_generator())
