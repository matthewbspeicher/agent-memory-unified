import logging
import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.auth import verify_api_key
from api.deps import get_broker
from broker.interfaces import Broker

logger = logging.getLogger(__name__)

router = APIRouter()
_start_time = time.time()


@router.get("/health")
def health(
    request: Request,
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    brokers_status = {}
    all_brokers = getattr(request.app.state, "brokers", {})
    settings = getattr(request.app.state, "settings", None)

    if all_brokers:
        for name, b in all_brokers.items():
            entry = {"connected": b.connection.is_connected()}
            if (
                name == "polymarket"
                and settings
                and getattr(settings, "polymarket_dry_run", False)
            ):
                entry["dry_run"] = True
            if (
                name == "kalshi"
                and settings
                and getattr(settings, "kalshi_demo", False)
            ):
                entry["demo"] = True
            brokers_status[name] = entry
    else:
        brokers_status["ibkr"] = {"connected": broker.connection.is_connected()}

    return {
        "status": "ok",
        "brokers": brokers_status,
        "uptime_seconds": round(time.time() - _start_time),
    }


@router.get("/health-internal")
async def health_internal(request: Request):
    db = getattr(request.app.state, "db", None)
    broker = getattr(request.app.state, "broker", None)
    all_brokers = getattr(request.app.state, "brokers", {})

    db_ok: bool | None = None
    if db is not None:
        try:
            await db.execute("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False

    broker_ok: bool | None = None
    reconnecting = False

    if all_brokers:
        broker_ok = any(b.connection.is_connected() for b in all_brokers.values())
        reconnecting = any(
            getattr(b.connection, "_reconnecting", False) for b in all_brokers.values()
        )
    elif broker is not None:
        reconnecting = getattr(broker.connection, "_reconnecting", False)
        broker_ok = broker.connection.is_connected()

    # Return 200 during an active reconnect attempt — don't let Docker restart
    # the container while the background reconnect loop is still running.
    if reconnecting:
        healthy = db_ok is not False
    else:
        healthy = (db_ok is not False) and (broker_ok is not False)

    # Bittensor subsystem health
    bt_health: dict = {"enabled": False}
    if getattr(request.app.state, "bittensor_enabled_runtime", False):
        bt_scheduler = getattr(request.app.state, "bittensor_scheduler", None)
        bt_evaluator = getattr(request.app.state, "bittensor_evaluator", None)
        bt_health = {
            "enabled": True,
            # Healthy if components exist — allow grace period at startup
            # (last_success_at will be None until first window fires)
            "healthy": bt_scheduler is not None and bt_evaluator is not None,
            "last_window_collected": (
                bt_scheduler.last_success_at.isoformat()
                if bt_scheduler and getattr(bt_scheduler, "last_success_at", None)
                else None
            ),
            "last_evaluation": (
                bt_evaluator.last_success_at.isoformat()
                if bt_evaluator and getattr(bt_evaluator, "last_success_at", None)
                else None
            ),
        }

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "healthy" if healthy else "unhealthy",
            "db": db_ok,
            "broker": broker_ok,
            "broker_reconnecting": reconnecting,
            "bittensor": bt_health,
        },
    )


@router.get("/health/connectivity")
async def health_connectivity(request: Request):
    """
    Perform a more rigorous health check by actually pinging broker APIs.
    This helps detect expired API keys or broker downtime.
    """
    all_brokers = getattr(request.app.state, "brokers", {})
    results = {}
    overall_healthy = True

    if not all_brokers:
        # Fallback to single primary broker if configured
        broker = getattr(request.app.state, "broker", None)
        if broker:
            all_brokers = {"primary": broker}

    for name, broker in all_brokers.items():
        health_status = False
        try:
            # Check if broker client has check_health (most prediction adapters do)
            if hasattr(broker, "client") and hasattr(broker.client, "check_health"):
                health_status = await broker.client.check_health()
            elif hasattr(broker, "check_health"):
                health_status = await broker.check_health()
            else:
                # Fallback: check basic connection flag
                health_status = broker.connection.is_connected()
        except Exception as e:
            logger.error(f"Health check failed for broker {name}: {e}")
            health_status = False

        results[name] = health_status
        if not health_status:
            overall_healthy = False

    return JSONResponse(
        status_code=200 if overall_healthy else 503,
        content={
            "status": "healthy" if overall_healthy else "degraded",
            "brokers": results,
        },
    )
