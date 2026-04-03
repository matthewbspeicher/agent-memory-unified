from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from api.auth import verify_api_key
from integrations.bittensor.scheduler import next_hash_window

router = APIRouter()


@router.get("/api/bittensor/status")
async def bittensor_status(
    request: Request,
    _: str = Depends(verify_api_key),
):
    enabled = getattr(request.app.state, "bittensor_enabled_runtime", False)
    if not enabled:
        return {"enabled": False}

    scheduler = getattr(request.app.state, "bittensor_scheduler", None)
    evaluator = getattr(request.app.state, "bittensor_evaluator", None)
    store = getattr(request.app.state, "bittensor_store", None)
    db = getattr(request.app.state, "db", None)

    # Scheduler section
    scheduler_data = {}
    if scheduler:
        now = datetime.now(tz=timezone.utc)
        scheduler_data = {
            "running": getattr(scheduler, "_running", False),
            "last_window_collected": (
                scheduler.last_success_at.isoformat()
                if getattr(scheduler, "last_success_at", None) else None
            ),
            "next_window": next_hash_window(now).isoformat(),
            "windows_collected_total": getattr(scheduler, "windows_collected_total", 0),
        }

    # Evaluator section
    evaluator_data = {}
    if evaluator:
        evaluator_data = {
            "running": getattr(evaluator, "_running", False),
            "last_evaluation": (
                evaluator.last_success_at.isoformat()
                if getattr(evaluator, "last_success_at", None) else None
            ),
            "unevaluated_windows": getattr(evaluator, "unevaluated_count", 0),
            "windows_evaluated_total": getattr(evaluator, "windows_evaluated_total", 0),
        }

    # Miners section
    miners_data: dict = {
        "total_in_metagraph": getattr(scheduler, "last_window_miner_count", 0) if scheduler else 0,
        "responded_last_window": getattr(scheduler, "last_window_responder_count", 0) if scheduler else 0,
        "response_rate": 0.0,
        "top_miners": [],
    }
    if miners_data["total_in_metagraph"] > 0:
        miners_data["response_rate"] = round(
            miners_data["responded_last_window"] / miners_data["total_in_metagraph"], 3
        )
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

    return {
        "enabled": True,
        "healthy": bool(scheduler and evaluator),
        "scheduler": scheduler_data,
        "evaluator": evaluator_data,
        "miners": miners_data,
        "agent": agent_data,
    }


@router.get("/api/bittensor/rankings")
async def bittensor_rankings(
    request: Request,
    limit: int = 50,
    _: str = Depends(verify_api_key),
):
    store = getattr(request.app.state, "bittensor_store", None)
    if not store:
        return {"rankings": [], "ranking_config": {}}
    rankings = await store.get_miner_rankings(limit=limit)
    ranking_config = getattr(request.app.state, "bittensor_ranking_config", {})
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
        "ranking_config": ranking_config,
    }


@router.get("/api/bittensor/miners/{hotkey}/accuracy")
async def bittensor_miner_accuracy(
    hotkey: str,
    request: Request,
    limit: int = 50,
    _: str = Depends(verify_api_key),
):
    store = getattr(request.app.state, "bittensor_store", None)
    if not store:
        return {"hotkey": hotkey, "records": []}
    records = await store.get_accuracy_for_miner(hotkey, limit=limit)
    return {
        "hotkey": hotkey,
        "records": [
            {
                "window_id": r.window_id,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "direction_correct": r.direction_correct,
                "predicted_return": r.predicted_return,
                "actual_return": r.actual_return,
                "magnitude_error": r.magnitude_error,
                "path_correlation": r.path_correlation,
                "outcome_bars": r.outcome_bars,
                "scoring_version": r.scoring_version,
                "evaluated_at": r.evaluated_at.isoformat(),
            }
            for r in records
        ],
    }


@router.get("/api/bittensor/signals")
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
