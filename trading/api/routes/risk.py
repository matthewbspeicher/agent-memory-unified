# api/routes/risk.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import verify_api_key
from api.deps import get_risk_engine

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


@router.patch("/rules")
async def update_rules(_: str = Depends(verify_api_key)):
    raise HTTPException(status_code=501, detail="Not implemented yet")
