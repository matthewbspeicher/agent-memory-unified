from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from api.auth import verify_api_key, verify_agent_token
from api.routes.bittensor_schemas import (
    BittensorMetricsResponse,
    BittensorRankingsResponse,
    BittensorSignalsResponse,
    BittensorStatusResponse,
)
from integrations.bittensor.scheduler import next_hash_window

router = APIRouter(prefix="/engine/v1/bittensor", tags=["bittensor"])


@router.get(
    "/status",
    response_model=BittensorStatusResponse,
    response_model_exclude_none=True,
)
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
            scheduler_data.update(
                {
                    "last_window_collected": (
                        scheduler.last_success_at.isoformat()
                        if getattr(scheduler, "last_success_at", None)
                        else None
                    ),
                    "next_window": next_hash_window(now).isoformat(),
                    "windows_collected_total": getattr(
                        scheduler, "windows_collected_total", 0
                    ),
                }
            )

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

    # Aggregator section
    aggregator = getattr(request.app.state, "consensus_aggregator", None)
    aggregator_data = aggregator.get_status() if aggregator else None

    # Intelligence Layer section
    intel_layer = getattr(request.app.state, "intelligence_layer", None)
    intel_data = intel_layer.get_status() if intel_layer else None

    return {
        "enabled": True,
        "healthy": bool(scheduler) or bool(bridge) or bool(aggregator),
        "scheduler": scheduler_data,
        "miners": miners_data,
        "agent": agent_data,
        "bridge": bridge_data,
        "consensus_aggregator": aggregator_data,
        "intelligence": intel_data,
    }


@router.get(
    "/rankings",
    response_model=BittensorRankingsResponse,
    response_model_exclude_none=True,
)
async def bittensor_rankings(
    request: Request,
    limit: int = 50,
    symbol: str | None = None,
    _: str = Depends(verify_api_key),
):
    store = getattr(request.app.state, "bittensor_store", None)
    if not store:
        return {"rankings": [], "ranking_config": {}}
    rankings = await store.get_miner_rankings(limit=limit, symbol=symbol)
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


@router.get(
    "/metrics",
    response_model=BittensorMetricsResponse,
    response_model_exclude_none=True,
)
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

    evaluator = getattr(request.app.state, "bittensor_evaluator", None)
    if evaluator and hasattr(evaluator, "metrics"):
        em = evaluator.metrics
        result["evaluator"] = {
            "windows_evaluated": em.windows_evaluated,
            "windows_expired": em.windows_expired,
            "windows_skipped": em.windows_skipped,
            "last_skip_reason": em.last_skip_reason,
            "last_evaluation_duration_secs": round(em.last_evaluation_duration_secs, 2),
        }

    weight_setter = getattr(request.app.state, "bittensor_weight_setter", None)
    if weight_setter and hasattr(weight_setter, "metrics"):
        wm = weight_setter.metrics
        result["weight_setter"] = {
            "weight_sets_total": wm.weight_sets_total,
            "weight_sets_failed": wm.weight_sets_failed,
            "weight_sets_skipped": wm.weight_sets_skipped,
            "last_weight_skip_reason": wm.last_weight_skip_reason,
            "last_weight_set_block": wm.last_weight_set_block,
            "last_weight_set_at": (
                wm.last_weight_set_at.isoformat()
                if wm.last_weight_set_at
                else None
            ),
            "last_weight_set_uid_count": wm.last_weight_set_uid_count,
        }

    return result


@router.get("/weight-set-log")
async def bittensor_weight_set_log(
    request: Request,
    limit: int = 50,
    _: str = Depends(verify_api_key),
):
    """Return the most recent weight-set attempts (audit trail).

    Useful for debugging "why didn't we set weights last cycle?" and for
    retrospective analysis of ranking→weight submissions.
    """
    store = getattr(request.app.state, "bittensor_store", None)
    if not store or not hasattr(store, "get_recent_weight_set_logs"):
        return {"entries": []}
    entries = await store.get_recent_weight_set_logs(limit=min(limit, 500))
    return {"entries": entries, "count": len(entries)}


@router.get(
    "/signals",
    response_model=BittensorSignalsResponse,
    response_model_exclude_none=True,
)
async def bittensor_signals(
    request: Request,
    symbol: str = "BTCUSD",
    timeframe: str = "5m",
    limit: int = 100,
    _: str = Depends(verify_api_key),
):
    store = getattr(request.app.state, "bittensor_store", None)
    if not store:
        return {"signals": []}
    views = await store.get_recent_views(symbol, timeframe, limit=limit)
    for v in views:
        if "is_low_confidence" in v:
            v["is_low_confidence"] = bool(v["is_low_confidence"])
    return {"signals": views}


@router.get("/kg/entity/{name}")
async def kg_entity(
    name: str,
    as_of: str | None = None,
    direction: str = "both",
    request: Request = None,
    agent_id: str = Depends(verify_agent_token),
):
    """Query knowledge graph for entity facts."""
    kg = getattr(request.app.state, "knowledge_graph", None)
    if not kg:
        return {"error": "Knowledge graph not initialized"}
    facts = await kg.query_entity(name, as_of=as_of, direction=direction)
    return {
        "entity": name,
        "facts": facts,
        "count": len(facts),
        "queried_by": agent_id
    }


@router.get("/kg/timeline")
async def kg_timeline(
    entity: str | None = None,
    limit: int = 50,
    request: Request = None,
    agent_id: str = Depends(verify_agent_token),
):
    """Get chronological timeline of KG facts."""
    kg = getattr(request.app.state, "knowledge_graph", None)
    if not kg:
        return {"error": "Knowledge graph not initialized"}
    tl = await kg.timeline(entity_name=entity, limit=limit)
    return {
        "entity": entity,
        "timeline": tl,
        "count": len(tl),
        "queried_by": agent_id
    }


@router.get("/kg/stats")
async def kg_stats(
    request: Request,
    agent_id: str = Depends(verify_agent_token),
):
    """Get knowledge graph statistics."""
    kg = getattr(request.app.state, "knowledge_graph", None)
    if not kg:
        return {"error": "Knowledge graph not initialized"}
    stats = await kg.stats()
    stats["queried_by"] = agent_id
    return stats
