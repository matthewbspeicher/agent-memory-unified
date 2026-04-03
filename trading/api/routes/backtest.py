"""Backtest API — runs strategies against historical data."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth import verify_api_key
from api.deps import get_agent_runner

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Backtest"], dependencies=[Depends(verify_api_key)])


class BacktestRequest(BaseModel):
    agent_name: str
    symbols: list[str] = ["AAPL", "MSFT", "GOOGL"]
    period: str = "6mo"


class SandboxRequest(BaseModel):
    """Evaluate an arbitrary strategy config against historical data.

    Unlike POST /backtest, this does NOT require a running agent — it
    creates a temporary agent from the strategy registry, evaluates it,
    and discards it. Designed for Hermes parameter exploration.
    """
    strategy: str
    parameters: dict = {}
    symbols: list[str] = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    universe: str | list[str] | None = None
    period: str = "6mo"
    initial_capital: float = 100000.0


@router.post("/backtest")
async def run_backtest(req: BacktestRequest, request: Request, runner=Depends(get_agent_runner)):
    """Run a backtest for an agent strategy against historical data."""
    from data.backtest import (
        BacktestEngine, HistoricalDataSource, ReplayDataBus, score_backtest_run,
    )
    from broker.models import Symbol, AssetType

    agent = runner._agents.get(req.agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{req.agent_name}' not found")

    data_bus = getattr(request.app.state, "data_bus", None)
    if not data_bus:
        raise HTTPException(status_code=501, detail="DataBus not available")

    # Fetch historical bars
    bars_by_symbol: dict = {}
    for ticker in req.symbols:
        sym = Symbol(ticker=ticker, asset_type=AssetType.STOCK)
        try:
            bars = await data_bus.get_historical(sym, timeframe="1d", period=req.period)
            if bars:
                bars_by_symbol[ticker] = bars
        except Exception as exc:
            logger.warning("Failed to fetch historical data for %s: %s", ticker, exc)

    if not bars_by_symbol:
        raise HTTPException(status_code=400, detail="No historical data available")

    # Build replay bus and engine
    hist_source = HistoricalDataSource(bars_by_symbol)
    replay_bus = ReplayDataBus(hist_source)
    engine = BacktestEngine(bus=replay_bus, agents=[agent])

    # Collect all timestamps across all symbols
    all_times = sorted({
        b.timestamp for bars in bars_by_symbol.values() for b in bars
    })

    raw = await engine.run(all_times)

    # Score the result using existing scorer
    result = score_backtest_run(
        agent_name=req.agent_name,
        parameters=agent.parameters if hasattr(agent, "parameters") else {},
        snapshots=raw["snapshots"],
        initial_equity=raw["initial_equity"],
        final_equity=raw["final_equity"],
    )

    # Persist using existing table schema
    db = getattr(request.app.state, "db", None)
    if db:
        await db.execute(
            """INSERT INTO backtest_results
               (agent_name, parameters, sharpe_ratio, profit_factor, total_pnl,
                max_drawdown, win_rate, total_trades, run_date, data_start, data_end)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.agent_name, json.dumps(result.parameters),
                result.sharpe_ratio, result.profit_factor, str(result.total_pnl),
                result.max_drawdown, result.win_rate, result.total_trades,
                result.run_date.isoformat(), str(result.data_start), str(result.data_end),
            ),
        )
        await db.commit()

    settings = getattr(request.app.state, "settings", None)
    min_sharpe = settings.backtest_min_sharpe if settings and hasattr(settings, "backtest_min_sharpe") else 1.0
    min_trades = settings.backtest_min_trades if settings and hasattr(settings, "backtest_min_trades") else 50

    return {
        "agent_name": result.agent_name,
        "total_trades": result.total_trades,
        "total_pnl": str(result.total_pnl),
        "win_rate": round(result.win_rate, 4),
        "sharpe_ratio": round(result.sharpe_ratio, 4),
        "max_drawdown": round(result.max_drawdown, 4),
        "profit_factor": round(result.profit_factor, 4),
        "is_deployable": result.is_deployable(min_sharpe=min_sharpe, min_trades=min_trades),
        "data_start": str(result.data_start),
        "data_end": str(result.data_end),
    }


@router.get("/backtest/results")
async def list_backtest_results(request: Request, agent_name: str | None = None, limit: int = 20):
    """Return stored backtest results, optionally filtered by agent."""
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=501, detail="Database not available")
    if agent_name:
        cursor = await db.execute(
            "SELECT * FROM backtest_results WHERE agent_name = ? ORDER BY run_date DESC LIMIT ?",
            (agent_name, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM backtest_results ORDER BY run_date DESC LIMIT ?", (limit,),
        )
    return [dict(r) for r in await cursor.fetchall()]


@router.post("/backtest/sandbox")
async def run_sandbox(req: SandboxRequest, request: Request):
    """Evaluate an arbitrary strategy config against historical data.

    Does NOT require a running agent — creates a temporary agent from the
    strategy registry, evaluates it against historical bars, and returns
    scored metrics. Designed for Hermes parameter exploration.
    """
    from backtesting.sandbox import BacktestSandbox

    data_bus = getattr(request.app.state, "data_bus", None)
    if not data_bus:
        raise HTTPException(status_code=501, detail="DataBus not available")

    sandbox = BacktestSandbox(data_bus=data_bus)
    result = await sandbox.evaluate(
        strategy=req.strategy,
        parameters=req.parameters,
        symbols=req.symbols,
        universe=req.universe,
        period=req.period,
        initial_capital=Decimal(str(req.initial_capital)),
    )

    if result.error:
        logger.warning("Sandbox evaluation error: %s", result.error)

    # Persist to backtest_results table
    db = getattr(request.app.state, "db", None)
    if db and not result.error:
        try:
            params_with_source = {**req.parameters, "_source": "sandbox"}
            await db.execute(
                """INSERT INTO backtest_results
                   (agent_name, parameters, sharpe_ratio, profit_factor, total_pnl,
                    max_drawdown, win_rate, total_trades, run_date, data_start, data_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"sandbox_{req.strategy}",
                    json.dumps(params_with_source),
                    result.sharpe_ratio,
                    result.profit_factor,
                    str(result.final_equity - result.initial_capital),
                    result.max_drawdown_pct / 100,
                    result.win_rate / 100,
                    result.total_trades,
                    datetime.now(timezone.utc).isoformat(),
                    req.period,
                    req.period,
                ),
            )
            await db.commit()
        except Exception as exc:
            logger.warning("Failed to persist sandbox result: %s", exc)

    return result.to_dict()

