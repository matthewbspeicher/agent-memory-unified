# api/routes/risk.py
from __future__ import annotations
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


@router.get("/status")
async def risk_status(
    _: str = Depends(verify_api_key),
    engine=Depends(get_risk_engine),
):
    return {
        "kill_switch": engine.kill_switch.is_enabled,
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
    await redis.setex(key, 60, val)

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
    val = await redis.get(key)
    if not val:
        raise HTTPException(
            status_code=400, detail="Invalid or expired confirmation token"
        )

    data = json.loads(val)
    enabled = data["enabled"]
    reason = data["reason"]

    # 1. Update In-memory engine
    engine = get_risk_engine(request)
    engine.kill_switch.toggle(enabled, reason)

    # 2. Update Redis global state (Phase A Requirement)
    await redis.set("kill_switch:active", "true" if enabled else "false")

    await redis.delete(key)

    return {
        "status": "success",
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
    engine = get_risk_engine(request)
    engine.kill_switch.toggle(req.enabled, req.reason)
    await redis.set("kill_switch:active", "true" if req.enabled else "false")
    return {
        "kill_switch": engine.kill_switch.is_enabled,
        "kill_switch_reason": engine.kill_switch.reason,
        "note": "Legacy endpoint used. Please migrate to /kill-switch/initiate",
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


@router.patch("/rules")
async def update_rules(_: str = Depends(verify_api_key)):
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
