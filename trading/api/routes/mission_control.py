"""Mission Control aggregation endpoint.

Single endpoint that returns everything the Mission Control dashboard needs:
- KPI summary (agents active, open trades, validator status, daily P&L)
- Per-service health (trading engine + external services from health_cache)
- Recent agent activity
- Bittensor scheduler/evaluator metrics snapshot

This is a pure aggregation over existing app.state resources — it does not
introduce new data sources. The frontend consumes one endpoint instead of
coordinating 4+ hooks.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Request

from api.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/engine/v1/mission-control",
    tags=["mission-control"],
    dependencies=[Depends(verify_api_key)],
)


def _status_value(status) -> str:
    """Return the lowercase string form of an AgentStatus enum (or "unknown")."""
    if status is None:
        return "unknown"
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


async def _agent_summary(request: Request) -> dict:
    """Aggregate agent roster status."""
    runner = getattr(request.app.state, "agent_runner", None)
    if runner is None:
        return {"total": 0, "running": 0, "stopped": 0, "error": 0, "agents": []}

    try:
        agents = runner.list_agents()
    except Exception as exc:
        logger.warning("agent_runner.list_agents() failed: %s", exc)
        return {"total": 0, "running": 0, "stopped": 0, "error": 0, "agents": []}

    statuses = [_status_value(getattr(a, "status", None)) for a in agents]

    return {
        "total": len(agents),
        "running": sum(1 for s in statuses if s == "running"),
        "stopped": sum(1 for s in statuses if s == "stopped"),
        "error": sum(1 for s in statuses if s == "error"),
        "agents": [
            {
                "name": a.name,
                "status": s,
                "shadow_mode": bool(
                    getattr(getattr(a, "config", None), "shadow_mode", False)
                ),
            }
            for a, s in zip(agents, statuses)
        ],
    }


async def _recent_activity(request: Request, limit: int = 10) -> list[dict]:
    """Recent opportunities from the store."""
    store = getattr(request.app.state, "opportunity_store", None)
    if store is None:
        return []
    try:
        return await store.list(limit=limit)
    except Exception as exc:
        logger.warning("opportunity_store.list() failed: %s", exc)
        return []


async def _open_trades_summary(request: Request) -> dict:
    """Aggregate open positions."""
    pnl_store = getattr(request.app.state, "pnl_store", None)
    if pnl_store is None:
        return {"count": 0, "unrealized_pnl": 0.0, "positions": []}

    try:
        positions = await pnl_store.list_open()
    except Exception as exc:
        logger.warning("pnl_store.list_open() failed: %s", exc)
        return {"count": 0, "unrealized_pnl": 0.0, "positions": []}

    total_pnl = 0.0
    for p in positions:
        pnl = p.get("unrealized_pnl") or 0
        try:
            total_pnl += float(pnl)
        except (TypeError, ValueError):
            pass

    return {
        "count": len(positions),
        "unrealized_pnl": round(total_pnl, 2),
        "positions": [
            {
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "quantity": p.get("quantity"),
                "entry_price": p.get("entry_price"),
                "unrealized_pnl": p.get("unrealized_pnl"),
                "agent_name": p.get("agent_name"),
            }
            for p in positions
        ],
    }


def _infra_health(request: Request) -> dict:
    """Read from health_cache — never blocks on network I/O."""
    services: list[dict] = [{"name": "trading_engine", "status": "healthy"}]
    health_cache = getattr(request.app.state, "health_cache", None)
    if health_cache is not None:
        try:
            for name, status in health_cache.all_statuses().items():
                entry = dict(status)
                entry["name"] = name
                services.append(entry)
        except Exception as exc:
            logger.warning("health_cache read failed: %s", exc)

    overall = (
        "healthy"
        if all(s.get("status") != "unhealthy" for s in services)
        else "degraded"
    )
    return {"status": overall, "services": services}


def _validator_snapshot(request: Request) -> dict:
    """Bittensor scheduler + evaluator metrics."""
    enabled = getattr(request.app.state, "bittensor_enabled_runtime", False)
    if not enabled:
        return {"enabled": False}

    snapshot: dict = {"enabled": True}

    scheduler = getattr(request.app.state, "bittensor_scheduler", None)
    if scheduler and hasattr(scheduler, "metrics"):
        m = scheduler.metrics
        snapshot["scheduler"] = {
            "windows_collected": m.windows_collected,
            "windows_failed": m.windows_failed,
            "last_miner_response_rate": round(m.last_miner_response_rate, 3),
            "consecutive_failures": m.consecutive_failures,
        }

    evaluator = getattr(request.app.state, "bittensor_evaluator", None)
    if evaluator and hasattr(evaluator, "metrics"):
        em = evaluator.metrics
        snapshot["evaluator"] = {
            "windows_evaluated": em.windows_evaluated,
            "windows_skipped": em.windows_skipped,
            "last_skip_reason": em.last_skip_reason,
        }

    return snapshot


@router.get("/status")
async def mission_control_status(request: Request):
    """Full dashboard snapshot — KPIs + per-panel data."""
    agents = await _agent_summary(request)
    trades = await _open_trades_summary(request)
    activity = await _recent_activity(request, limit=10)
    infra = _infra_health(request)
    validator = _validator_snapshot(request)

    system_status = infra["status"]

    return {
        "kpis": {
            "system_status": system_status,
            "agents_active": agents["running"],
            "agents_total": agents["total"],
            "open_trades": trades["count"],
            "unrealized_pnl": trades["unrealized_pnl"],
            "validator_enabled": validator.get("enabled", False),
        },
        "infra": infra,
        "agents": agents,
        "activity": activity,
        "trades": trades,
        "validator": validator,
    }
