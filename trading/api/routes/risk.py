# api/routes/risk.py
from __future__ import annotations
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import verify_api_key
from api.deps import get_risk_engine, get_risk_analytics, get_broker

router = APIRouter(prefix="/risk", tags=["risk"])


class KillSwitchRequest(BaseModel):
    enabled: bool
    reason: str = ""


@router.get("/status")
async def risk_status(_: str = Depends(verify_api_key)):
    engine = get_risk_engine()
    return {
        "kill_switch": engine.kill_switch.is_enabled,
        "kill_switch_reason": engine.kill_switch.reason,
        "rules": [{"name": r.name} for r in engine.rules],
    }


@router.post("/kill-switch")
async def toggle_kill_switch(req: KillSwitchRequest, _: str = Depends(verify_api_key)):
    engine = get_risk_engine()
    engine.kill_switch.toggle(req.enabled, req.reason)
    return {
        "kill_switch": engine.kill_switch.is_enabled,
        "kill_switch_reason": engine.kill_switch.reason,
    }


@router.get("/analytics")
async def risk_analytics(_: str = Depends(verify_api_key)):
    """Get real-time portfolio risk metrics (VaR, drawdown, leverage, exposure)."""
    risk_analytics = get_risk_analytics()
    if not risk_analytics:
        raise HTTPException(status_code=503, detail="RiskAnalytics not initialized")

    broker = get_broker()
    positions = broker.get_positions() if hasattr(broker, "get_positions") else []

    # Build price map
    prices = {}
    for pos in positions:
        if "symbol" in pos and "current_price" in pos:
            prices[pos["symbol"]] = Decimal(str(pos["current_price"]))

    portfolio_risk = risk_analytics.calculate_portfolio_risk(positions, prices)
    violations = risk_analytics.check_limits(portfolio_risk)

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
