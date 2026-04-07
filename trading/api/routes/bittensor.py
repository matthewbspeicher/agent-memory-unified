from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from api.auth import verify_api_key
from api.routes.bittensor_schemas import (
    BittensorMetricsResponse,
    BittensorRankingsResponse,
    BittensorSignalsResponse,
    BittensorStatusResponse,
)
from integrations.bittensor.scheduler import next_hash_window

router = APIRouter()


@router.get("/api/bittensor/status", response_model=BittensorStatusResponse, response_model_exclude_none=True)
async def bittensor_status(
    request: Request,
    _: str = Depends(verify_api_key),
):
    enabled = getattr(request.app.state, "bittensor_enabled_runtime", False)
    if not enabled:
        return {"enabled": False}

    scheduler = getattr(request.app.state, "bittensor_scheduler", None)
    store = getattr(request.app.state, "bittensor_store", None)
    db = getattr(request.app.state, "db", None)

    # Scheduler section (direct dendrite queries — disabled by default)
    scheduler_data = {}
    if scheduler:
        direct_query_enabled = getattr(scheduler, "_direct_query_enabled", False)
        now = datetime.now(tz=timezone.utc)
        scheduler_data = {
            "running": getattr(scheduler, "_running", False),
            "direct_query_enabled": direct_query_enabled,
        }
        if direct_query_enabled:
            scheduler_data.update({
                "last_window_collected": (
                    scheduler.last_success_at.isoformat()
                    if getattr(scheduler, "last_success_at", None)
                    else None
                ),
                "next_window": next_hash_window(now).isoformat(),
                "windows_collected_total": getattr(scheduler, "windows_collected_total", 0),
            })

    # Miners section
    direct_query_on = scheduler and getattr(scheduler, "_direct_query_enabled", False)
    miners_data: dict = {
        "total_in_metagraph": getattr(scheduler, "last_window_miner_count", 0)
        if scheduler
        else 0,
        "top_miners": [],
    }
    if direct_query_on:
        miners_data["responded_last_window"] = getattr(
            scheduler, "last_window_responder_count", 0
        )
        if miners_data["total_in_metagraph"] > 0:
            miners_data["response_rate"] = round(
                miners_data["responded_last_window"]
                / miners_data["total_in_metagraph"],
                3,
            )
        else:
            miners_data["response_rate"] = 0.0
    if store:
        rankings = await store.get_miner_rankings(limit=10)
        miners_data["top_miners"] = [
            {
                "hotkey": r.miner_hotkey,
                "hybrid_score": round(r.hybrid_score, 4),
                "direction_accuracy": round(r.direction_accuracy, 4),
                "windows_evaluated": r.windows_evaluated,
            }
            for r in rankings
        ]

    # Agent section — raw SQL queries using existing idx_opp_agent index
    agent_data: dict = {
        "name": "bittensor_btc_5m",
        "opportunities_emitted": 0,
        "last_opportunity": None,
    }
    if db:
        try:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt, MAX(created_at) as latest "
                "FROM opportunities WHERE agent_name = ?",
                ("bittensor_btc_5m",),
            )
            row = await cursor.fetchone()
            if row:
                agent_data["opportunities_emitted"] = row["cnt"] or 0
                agent_data["last_opportunity"] = row["latest"]
        except Exception:
            pass

    # Taoshi Bridge section
    bridge = getattr(request.app.state, "taoshi_bridge", None)
    bridge_data = bridge.get_status() if bridge else None

    return {
        "enabled": True,
        "healthy": bool(scheduler) or bool(bridge),
        "scheduler": scheduler_data,
        "miners": miners_data,
        "agent": agent_data,
        "bridge": bridge_data,
    }


@router.get("/api/bittensor/rankings", response_model=BittensorRankingsResponse, response_model_exclude_none=True)
async def bittensor_rankings(
    request: Request,
    limit: int = 50,
    _: str = Depends(verify_api_key),
):
    store = getattr(request.app.state, "bittensor_store", None)
    if not store:
        return {"rankings": [], "ranking_config": {}}
    rankings = await store.get_miner_rankings(limit=limit)
    return {
        "rankings": [
            {
                "miner_hotkey": r.miner_hotkey,
                "hybrid_score": r.hybrid_score,
                "direction_accuracy": r.direction_accuracy,
                "mean_magnitude_error": r.mean_magnitude_error,
                "mean_path_correlation": r.mean_path_correlation,
                "internal_score": r.internal_score,
                "latest_incentive_score": r.latest_incentive_score,
                "windows_evaluated": r.windows_evaluated,
                "alpha_used": r.alpha_used,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rankings
        ],
        "ranking_config": {},
    }


@router.get("/api/bittensor/metrics", response_model=BittensorMetricsResponse, response_model_exclude_none=True)
async def bittensor_metrics(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Return raw observability metrics from scheduler."""
    enabled = getattr(request.app.state, "bittensor_enabled_runtime", False)
    if not enabled:
        return {"enabled": False}

    result: dict = {"enabled": True}

    scheduler = getattr(request.app.state, "bittensor_scheduler", None)
    if scheduler and hasattr(scheduler, "metrics"):
        m = scheduler.metrics
        result["scheduler"] = {
            "windows_collected": m.windows_collected,
            "windows_failed": m.windows_failed,
            "hash_verifications_passed": m.hash_verifications_passed,
            "hash_verifications_failed": m.hash_verifications_failed,
            "last_collection_duration_secs": round(m.last_collection_duration_secs, 2),
            "avg_collection_duration_secs": round(m.avg_collection_duration_secs, 2),
            "last_miner_response_rate": round(m.last_miner_response_rate, 3),
            "consecutive_failures": m.consecutive_failures,
        }

    return result


@router.get("/api/bittensor/signals", response_model=BittensorSignalsResponse, response_model_exclude_none=True)
async def bittensor_signals(
    request: Request,
    symbol: str = "BTCUSD",
    timeframe: str = "5m",
    limit: int = 100,
    _: str = Depends(verify_api_key),
):
    store = getattr(request.app.state, "bittensor_store", None)
    if not store:
        return {"symbol": symbol, "timeframe": timeframe, "views": []}
    views = await store.get_recent_views(symbol, timeframe, limit=limit)
    for v in views:
        if "is_low_confidence" in v:
            v["is_low_confidence"] = bool(v["is_low_confidence"])
    return {"signals": views}
