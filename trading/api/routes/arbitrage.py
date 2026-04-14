"""Arbitrage and Capital Governor API routes."""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from api.auth import verify_api_key

router = APIRouter(tags=["Arbitrage"], dependencies=[Depends(verify_api_key)])


class ExecuteArbRequest(BaseModel):
    observation_id: int
    agent_name: str
    sequencing: Optional[str] = "less_liquid_first"


@router.get("/arb/spreads")
async def get_active_spreads(request: Request, min_gap: int = 5, limit: int = 50):
    """List active spread opportunities from the SpreadStore."""
    spread_store = getattr(request.app.state, "spread_store", None)
    if not spread_store:
        raise HTTPException(status_code=501, detail="SpreadStore not configured")

    spreads = await spread_store.get_top_spreads(min_gap=min_gap, limit=limit)
    return {"spreads": spreads, "count": len(spreads)}


@router.post("/arb/execute")
async def execute_arbitrage(req: ExecuteArbRequest, request: Request):
    """Atomically execute a dual-leg arbitrage trade."""
    spread_store = getattr(request.app.state, "spread_store", None)
    arb_coordinator = getattr(request.app.state, "arb_coordinator", None)

    if not spread_store or not arb_coordinator:
        raise HTTPException(
            status_code=501, detail="Arbitrage executioner not configured"
        )

    # 1. Claim the spread
    success = await spread_store.claim_spread(req.observation_id, req.agent_name)
    if not success:
        raise HTTPException(status_code=409, detail="Spread already claimed or expired")

    try:
        # 2. Fetch observation data
        observation = await spread_store.get_observation(req.observation_id)
        if not observation:
            await spread_store.release_spread(req.observation_id)
            raise HTTPException(status_code=404, detail="Observation not found")

        # 3. Build ArbTrade from observation
        from decimal import Decimal
        from uuid import uuid4
        from execution.models import ArbTrade, ArbLeg, SequencingStrategy
        from broker.models import MarketOrder, OrderSide, Symbol, AssetType

        sequencing = SequencingStrategy(req.sequencing)
        trade_id = f"arb-{uuid4().hex[:12]}"

        # Determine order sides based on pricing (sell high, buy low)
        kalshi_cents = observation["kalshi_cents"]
        poly_cents = observation["poly_cents"]

        # Leg A: Kalshi
        leg_a = ArbLeg(
            broker_id="kalshi",
            order=MarketOrder(
                symbol=Symbol(
                    ticker=observation["kalshi_ticker"], asset_type=AssetType.PREDICTION
                ),
                side=OrderSide.BUY if kalshi_cents <= poly_cents else OrderSide.SELL,
                quantity=Decimal("1"),
                account_id="default",
            ),
        )

        # Leg B: Polymarket
        leg_b = ArbLeg(
            broker_id="polymarket",
            order=MarketOrder(
                symbol=Symbol(
                    ticker=observation["poly_ticker"], asset_type=AssetType.PREDICTION
                ),
                side=OrderSide.SELL if kalshi_cents <= poly_cents else OrderSide.BUY,
                quantity=Decimal("1"),
                account_id="default",
            ),
        )

        trade = ArbTrade(
            id=trade_id,
            symbol_a=observation["kalshi_ticker"],
            symbol_b=observation["poly_ticker"],
            leg_a=leg_a,
            leg_b=leg_b,
            expected_profit_bps=observation["gap_cents"],
            sequencing=sequencing,
        )

        # 4. Execute the arbitrage
        success = await arb_coordinator.execute_arbitrage(trade)

        return {
            "status": "completed" if success else "failed",
            "trade_id": trade_id,
            "observation_id": req.observation_id,
            "symbol_a": trade.symbol_a,
            "symbol_b": trade.symbol_b,
            "expected_profit_bps": trade.expected_profit_bps,
            "state": trade.state.value,
        }
    except Exception as e:
        await spread_store.release_spread(req.observation_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/arb/governor/config")
async def get_governor_config(request: Request):
    """Return the current Capital Governor configuration."""
    risk_engine = getattr(request.app.state, "risk_engine", None)
    if not risk_engine or not risk_engine._governor:
        raise HTTPException(status_code=501, detail="Governor not configured")

    config = risk_engine._governor._gov_config
    return config.__dict__


@router.get("/arb/pnl")
async def get_arb_pnl(request: Request):
    """Return realized P&L from completed arbitrage trades."""
    arb_store = getattr(request.app.state, "arb_store", None)
    if not arb_store:
        raise HTTPException(status_code=501, detail="Arbitrage store not configured")

    # In a real system, we'd query the DB for completed ArbTrades
    # and sum their leg fill P&Ls.
    # For MVP, we'll return a placeholder or implement a basic sum logic if trades are tracked.

    # Query ArbStore for completed trades (simplified for now)
    cursor = await arb_store._db.execute(
        "SELECT COUNT(*) as count FROM arb_trades WHERE state = 'completed'"
    )
    row = await cursor.fetchone()
    completed_count = row[0] if row else 0

    # Placeholder P&L - will be wired to actual fill data in Task 14/15
    return {"total_pnl": 0.0, "completed_trades": completed_count, "currency": "USD"}


@router.get("/arb/governor/status")
async def get_governor_status(request: Request):
    """Return the current Sharpe ratios and position limits for all agents."""
    risk_engine = getattr(request.app.state, "risk_engine", None)
    if not risk_engine or not risk_engine._governor:
        raise HTTPException(status_code=501, detail="Governor not configured")

    gov = risk_engine._governor
    await gov._refresh_cache_if_needed()

    if not gov._cache:
        return {"agents": [], "status": "cache_warming"}

    results = []
    for agent_name, ranking in gov._cache.rankings.items():
        stage = gov._cache.stages.get(agent_name, 0)

        # Re-calculate size factor logic for transparency
        sharpe_ratio = ranking.sharpe_ratio
        sharpe_mult = max(0.1, sharpe_ratio / gov._gov_config.min_sharpe_for_promotion)
        stage_mult = max(0.1, stage / 3.0)
        size_factor = max(
            0.1, min(1.0, sharpe_mult * stage_mult * gov._gov_config.scaling_factor)
        )

        results.append(
            {
                "agent_name": agent_name,
                "sharpe_ratio": round(sharpe_ratio, 2),
                "tournament_stage": stage,
                "size_factor": round(size_factor, 2),
                "max_allocation_usd": round(
                    gov._gov_config.base_allocation_usd * size_factor, 2
                ),
            }
        )

    return {"agents": results, "timestamp": gov._cache.timestamp}


@router.post("/arb/executor/enable")
async def enable_arb_executor(request: Request):
    """Enable auto-execution of arbitrage spreads."""
    arb_executor = getattr(request.app.state, "arb_executor", None)
    if not arb_executor:
        raise HTTPException(status_code=501, detail="ArbExecutor not configured")
    arb_executor.set_enabled(True)
    return {"status": "enabled"}


@router.post("/arb/executor/disable")
async def disable_arb_executor(request: Request):
    """Disable auto-execution of arbitrage spreads."""
    arb_executor = getattr(request.app.state, "arb_executor", None)
    if not arb_executor:
        raise HTTPException(status_code=501, detail="ArbExecutor not configured")
    arb_executor.set_enabled(False)
    return {"status": "disabled"}


@router.get("/arb/executor/status")
async def get_arb_executor_status(request: Request):
    """Return the current status of the ArbExecutor."""
    arb_executor = getattr(request.app.state, "arb_executor", None)
    if not arb_executor:
        raise HTTPException(status_code=501, detail="ArbExecutor not configured")
    return {
        "enabled": arb_executor._enabled,
        "min_profit_bps": arb_executor._min_profit_bps,
        "max_position_usd": arb_executor._max_position_usd,
        "active_trades": len(arb_executor._active_trades),
    }
