# trading/api/routes/competition.py
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

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
