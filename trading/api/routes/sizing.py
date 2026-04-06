"""Sizing API — recommended position size for an agent."""

from __future__ import annotations
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import verify_api_key
from api.deps import get_agent_runner

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Sizing"], dependencies=[Depends(verify_api_key)])


@router.get("/sizing/{agent_name}")
async def get_sizing(
    agent_name: str,
    request: Request,
    price: float = 100.0,
    runner=Depends(get_agent_runner),
):
    """Return the recommended quantity for an agent trade at a given price."""
    sizing = getattr(request.app.state, "sizing_engine", None)
    if not sizing:
        raise HTTPException(status_code=501, detail="Sizing engine not configured")

    agent = runner._agents.get(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    data_bus = getattr(request.app.state, "data_bus", None)
    bankroll = Decimal("100000")
    if data_bus:
        try:
            bal = await data_bus.get_balances()
            if bal:
                bankroll = bal.buying_power or bal.cash or bankroll
        except Exception:
            pass

    trust_level = agent.config.trust_level
    qty = await sizing.compute_size(
        agent_name, trust_level, Decimal(str(price)), bankroll
    )

    return {
        "agent_name": agent_name,
        "recommended_quantity": str(qty),
        "price": str(price),
        "bankroll": str(bankroll),
        "trust_level": trust_level.value,
    }
