# api/routes/risk.py
from __future__ import annotations
import json
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth import verify_api_key
from api.dependencies import get_broker, get_risk_engine, get_risk_analytics, get_redis
from api.identity.dependencies import require_scope
from utils.audit import audit_event

router = APIRouter(prefix="/risk", tags=["risk"])


class KillSwitchRequest(BaseModel):
    enabled: bool
    reason: str = ""


async def _set_halted(request: Request, redis, enabled: bool, reason: str) -> list[str]:
    engine = get_risk_engine(request)
    engine.bind_control_store(redis)
    brokers = getattr(request.app.state, "brokers", None)
    if not brokers:
        broker = getattr(request.app.state, "broker", None)
        brokers = {"primary": broker} if broker is not None else {}
    engine.register_brokers(brokers)
    try:
        return await engine.set_halted(enabled, reason)
    except Exception as exc:
        raise HTTPException(
            503, "Trading control update failed; execution remains blocked"
        ) from exc


@router.get("/status")
async def risk_status(
    request: Request,
    _: str = Depends(verify_api_key),
    engine=Depends(get_risk_engine),
):
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        engine.bind_control_store(redis)
        try:
            await engine.sync_halt()
        except Exception as exc:
            raise HTTPException(503, "Trading control state unavailable") from exc
    return {
        "kill_switch": engine.check_kill_active(),
        "kill_switch_reason": engine.kill_switch.reason,
        "rules": [{"name": r.name} for r in engine.rules],
    }


@router.post(
    "/kill-switch/initiate", dependencies=[Depends(require_scope("risk:halt"))]
)
@audit_event("risk.kill_switch.initiate")
async def initiate_kill_switch(
    req: KillSwitchRequest,
    request: Request,
    redis=Depends(get_redis),
):
    """Step 1: Initiate kill-switch toggle and get confirmation token."""
    import uuid

    token = str(uuid.uuid4())
    # Store token in redis for 60s
    key = f"kill_switch:token:{token}"
    val = json.dumps({"enabled": req.enabled, "reason": req.reason})
    try:
        await redis.setex(key, 60, val)
    except Exception as exc:
        raise HTTPException(503, "Trading control state unavailable") from exc

    return {
        "confirmation_token": token,
        "expires_in": 60,
        "action": "HALT" if req.enabled else "RESUME",
        "reason": req.reason,
    }


@router.post("/kill-switch/confirm", dependencies=[Depends(require_scope("risk:halt"))])
@audit_event("risk.kill_switch.confirm")
async def confirm_kill_switch(
    token: str,
    request: Request,
    redis=Depends(get_redis),
):
    """Step 2: Confirm kill-switch toggle using the token."""
    key = f"kill_switch:token:{token}"
    # Consume once atomically so concurrent confirmations cannot replay a resume.
    try:
        val = await redis.getdel(key)
    except Exception as exc:
        raise HTTPException(503, "Trading control state unavailable") from exc
    if not val:
        raise HTTPException(
            status_code=400, detail="Invalid or expired confirmation token"
        )

    try:
        data = KillSwitchRequest.model_validate_json(val)
    except ValueError as exc:
        raise HTTPException(400, "Invalid confirmation token payload") from exc
    enabled = data.enabled
    reason = data.reason

    failures = await _set_halted(request, redis, enabled, reason)

    return {
        "status": "success" if not failures else "halted_with_cancellation_failures",
        "cancellation_failures": failures,
        "kill_switch": enabled,
        "kill_switch_reason": reason,
    }


@router.post("/kill-switch", dependencies=[Depends(require_scope("risk:halt"))])
@audit_event("risk.kill_switch.legacy")
async def toggle_kill_switch(
    req: KillSwitchRequest,
    request: Request,
    redis=Depends(get_redis),
):
    """Legacy endpoint — now requires confirmation for enabling."""
    # If disabling, allow immediate. If enabling, force two-step or allow with warning.
    # For Phase A, we still allow legacy for now but emit a warning.
    failures = await _set_halted(request, redis, req.enabled, req.reason)
    engine = get_risk_engine(request)
    return {
        "kill_switch": engine.kill_switch.is_enabled,
        "kill_switch_reason": engine.kill_switch.reason,
        "note": "Legacy endpoint used. Please migrate to /kill-switch/initiate",
        "cancellation_failures": failures,
    }


@router.get("/analytics")
async def risk_analytics(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Get real-time portfolio risk metrics (VaR, drawdown, leverage, exposure)."""
    analytics = get_risk_analytics(request)
    if not analytics:
        raise HTTPException(status_code=503, detail="RiskAnalytics not initialized")

    broker = get_broker(request)
    positions = broker.get_positions() if hasattr(broker, "get_positions") else []

    # Build price map
    prices = {}
    for pos in positions:
        if "symbol" in pos and "current_price" in pos:
            prices[pos["symbol"]] = Decimal(str(pos["current_price"]))

    portfolio_risk = analytics.calculate_portfolio_risk(positions, prices)
    violations = analytics.check_limits(portfolio_risk)

    return {
        "timestamp": portfolio_risk.timestamp.isoformat(),
        "positions": {
            "total": portfolio_risk.total_positions,
            "long": portfolio_risk.long_positions,
            "short": portfolio_risk.short_positions,
        },
        "notional": {
            "long": str(portfolio_risk.total_long_notional),
            "short": str(portfolio_risk.total_short_notional),
            "net": str(portfolio_risk.net_notional),
            "gross": str(portfolio_risk.gross_notional),
        },
        "var": {
            "95": str(portfolio_risk.portfolio_var_95),
            "99": str(portfolio_risk.portfolio_var_99),
            "cvar": str(portfolio_risk.portfolio_cvar),
        },
        "drawdown": {
            "current": str(portfolio_risk.current_drawdown),
            "max": str(portfolio_risk.max_drawdown),
            "peak_equity": str(portfolio_risk.peak_equity),
            "current_equity": str(portfolio_risk.current_equity),
        },
        "leverage": {
            "current": str(portfolio_risk.current_leverage),
            "max": str(portfolio_risk.max_leverage),
        },
        "violations": [
            {
                "limit": v.limit_name,
                "current": v.current_value,
                "limit_value": v.limit_value,
                "severity": v.severity,
                "message": v.message,
            }
            for v in violations
        ],
    }


@router.patch("/rules", dependencies=[Depends(require_scope("risk:halt"))])
async def update_rules():
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/portfolio-drawdown")
async def get_portfolio_drawdown_status(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Get portfolio drawdown status and high-water mark."""
    store = getattr(request.app.state, "portfolio_state_store", None)
    if not store:
        raise HTTPException(
            status_code=503, detail="Portfolio state store not initialized"
        )

    state = await store.get_state("portfolio_drawdown")

    return {
        "high_water_mark": float(state.high_water_mark) if state else 0.0,
        "triggered": state.triggered if state else False,
        "triggered_at": state.triggered_at.isoformat()
        if state and state.triggered_at
        else None,
        "cooldown_hours": 24,
    }


@router.get(
    "/execution/recovery",
    dependencies=[Depends(require_scope("risk:halt")), Depends(require_scope("write:orders"))],
)
async def execution_recovery_status(request: Request):
    """Inspect the blocked dispatch before explicit recovery."""
    from api.dependencies import get_execution_service
    try:
        return await get_execution_service(request).reconciliation_status()
    except Exception as exc:
        raise HTTPException(503, "Execution recovery state unavailable") from exc


class ExecutionRecoveryRequest(BaseModel):
    token: str


@router.post(
    "/execution/recovery",
    dependencies=[Depends(require_scope("risk:halt")), Depends(require_scope("write:orders"))],
)
@audit_event("risk.execution.recover")
async def recover_execution(req: ExecutionRecoveryRequest, request: Request):
    """Reconcile the exact dispatch while halted; never resume or submit orders."""
    from api.dependencies import get_execution_service
    from execution.service import ExecutionRejected, ExecutionUnavailable
    try:
        return await get_execution_service(request).recover(req.token)
    except ExecutionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ExecutionRejected as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "Recovery response unavailable; inspect recovery status before retrying") from exc
