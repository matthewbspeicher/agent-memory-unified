"""Prediction markets browser endpoints."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from fastapi import APIRouter, Request, Depends, Query

from api.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_contract(c) -> dict:
    d = asdict(c)
    if d.get("close_time"):
        d["close_time"] = d["close_time"].isoformat()
    return d


async def _fetch_kalshi(source) -> list:
    try:
        return await source.get_markets(max_pages=3)
    except Exception as e:
        logger.error("Failed to fetch Kalshi markets: %s", e)
        return []


async def _fetch_polymarket(source) -> list:
    try:
        return await source.get_markets()
    except Exception as e:
        logger.error("Failed to fetch Polymarket markets: %s", e)
        return []


async def _noop() -> list:
    return []


@router.get("/markets")
async def list_prediction_markets(
    request: Request,
    include_matches: bool = Query(False),
    _: str = Depends(verify_api_key),
):
    bus = getattr(request.app.state, "data_bus", None)
    if not bus:
        return {"kalshi": [], "polymarket": []}

    kalshi_source = getattr(bus, "_kalshi_source", None)
    poly_source = getattr(bus, "_polymarket_source", None)

    kalshi_contracts, poly_contracts = await asyncio.gather(
        _fetch_kalshi(kalshi_source) if kalshi_source else _noop(),
        _fetch_polymarket(poly_source) if poly_source else _noop(),
    )

    response: dict = {
        "kalshi": [_serialize_contract(c) for c in kalshi_contracts],
        "polymarket": [_serialize_contract(c) for c in poly_contracts],
    }

    if include_matches:
        from strategies.matching import match_markets
        candidates = match_markets(kalshi_contracts, poly_contracts, min_score=0.35)
        k_lookup = {m.ticker: m for m in kalshi_contracts}
        p_lookup = {m.ticker: m for m in poly_contracts}
        matches = []
        for cand in candidates:
            k = k_lookup.get(cand.kalshi_ticker)
            p = p_lookup.get(cand.poly_ticker)
            if not k or not p:
                continue
            k_cents = k.yes_bid or 0
            p_cents = p.yes_bid or 0
            matches.append({
                "kalshi_ticker": cand.kalshi_ticker,
                "poly_ticker": cand.poly_ticker,
                "final_score": round(cand.final_score, 4),
                "kalshi_cents": k_cents,
                "poly_cents": p_cents,
                "gap_cents": abs(k_cents - p_cents),
            })
        response["matches"] = matches

    return response


@router.get("/markets/spreads/history")
async def spread_history(
    request: Request,
    kalshi_ticker: str = Query(...),
    poly_ticker: str = Query(...),
    hours: int = Query(24, ge=1, le=168),
    _: str = Depends(verify_api_key),
):
    spread_store = getattr(request.app.state, "spread_store", None)
    if not spread_store:
        return {
            "kalshi_ticker": kalshi_ticker,
            "poly_ticker": poly_ticker,
            "observations": [],
            "max_gap": 0,
            "min_gap": 0,
            "current_gap": 0,
        }

    history = await spread_store.get_history(kalshi_ticker, poly_ticker, hours=hours)
    observations = [
        {
            "observed_at": obs.observed_at,
            "kalshi_cents": obs.kalshi_cents,
            "poly_cents": obs.poly_cents,
            "gap_cents": obs.gap_cents,
        }
        for obs in history
    ]
    gaps = [obs.gap_cents for obs in history]
    return {
        "kalshi_ticker": kalshi_ticker,
        "poly_ticker": poly_ticker,
        "observations": observations,
        "max_gap": max(gaps, default=0),
        "min_gap": min(gaps, default=0),
        "current_gap": gaps[-1] if gaps else 0,
    }


@router.get("/markets/spreads/top")
async def top_spreads(
    request: Request,
    min_gap: int = Query(5, ge=0),
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    spread_store = getattr(request.app.state, "spread_store", None)
    if not spread_store:
        return []
    return await spread_store.get_top_spreads(min_gap=min_gap, limit=limit)


@router.get("/markets/kalshi/positions")
async def list_kalshi_paper_positions(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Return open Kalshi paper positions with entry price and unrealized P&L estimate."""
    from storage.paper import PaperStore
    from broker.models import AssetType

    paper_store: PaperStore | None = getattr(request.app.state, "paper_store", None)
    if not paper_store:
        return {"positions": []}

    try:
        positions = await paper_store.get_positions("KALSHI_PAPER")
        result = []
        for p in positions:
            if p.symbol.asset_type != AssetType.PREDICTION:
                continue
            result.append({
                "ticker": p.symbol.ticker,
                "quantity": float(p.quantity),
                "avg_cost": float(p.avg_cost),
                "realized_pnl": float(p.realized_pnl),
            })
        return {"positions": result}
    except Exception as exc:
        logger.error("kalshi/positions failed: %s", exc)
        return {"positions": []}


@router.get("/markets/kalshi/signals")
async def list_kalshi_signals(
    request: Request,
    limit: int = 50,
    _: str = Depends(verify_api_key),
):
    """Return recent NewsSignals from the in-process news source (in-memory only)."""
    bus = getattr(request.app.state, "data_bus", None)
    if not bus:
        return {"signals": []}
    news_source = getattr(bus, "_news_source", None)
    if not news_source:
        return {"signals": []}
    return {"signals": [], "note": "signals are streamed via EventBus; historical store not yet implemented"}
