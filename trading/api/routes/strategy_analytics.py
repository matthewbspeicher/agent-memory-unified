"""Strategy analytics API routes — scorecard, drilldown, trades, symbols."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request

from analytics.models import StrategyDrilldown
from analytics.strategy_scorecard import (
    compute_equity_curve,
    compute_exit_reason_breakdown,
    compute_rolling_expectancy,
    compute_summary,
    compute_symbol_breakdown,
)
from api.auth import verify_api_key
from storage.trade_analytics import TradeAnalyticsStore

router = APIRouter(prefix="/analytics/strategies", tags=["strategy-analytics"])

_WINDOW_DELTAS = {
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


def _window_start(window: str) -> str | None:
    delta = _WINDOW_DELTAS.get(window)
    if delta is None:
        return None
    return (datetime.now(timezone.utc) - delta).isoformat()


def _get_store(request: Request) -> TradeAnalyticsStore:
    return TradeAnalyticsStore(request.app.state.db)


# Register scorecard BEFORE {agent_name} to avoid FastAPI matching "scorecard" as a path param.
def _filter_by_regime(
    trades: list[dict],
    trend_regime: str | None = None,
    volatility_regime: str | None = None,
    liquidity_regime: str | None = None,
) -> list[dict]:
    """Filter trade rows by regime dimensions (flat columns on trade_analytics)."""
    if not any([trend_regime, volatility_regime, liquidity_regime]):
        return trades
    result = []
    for t in trades:
        if trend_regime and t.get("trend_regime") != trend_regime:
            continue
        if volatility_regime and t.get("volatility_regime") != volatility_regime:
            continue
        if liquidity_regime and t.get("liquidity_regime") != liquidity_regime:
            continue
        result.append(t)
    return result


@router.get("/scorecard")
async def get_scorecard(
    request: Request,
    window: str = Query("all", pattern="^(7d|30d|90d|all)$"),
    broker_id: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    trend_regime: str | None = Query(None, description="Filter by trend_regime: uptrend|downtrend|range"),
    volatility_regime: str | None = Query(None, description="Filter by volatility_regime: low|medium|high"),
    liquidity_regime: str | None = Query(None, description="Filter by liquidity_regime: low|medium|high"),
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query("expectancy", pattern="^(expectancy|net_pnl|win_rate|profit_factor)$"),
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    ws = _window_start(window)
    strategies = await store.get_distinct_strategies()

    summaries = []
    for agent_name in strategies:
        trades = await store.list_by_strategy(agent_name, window_start=ws, limit=10_000)
        if broker_id:
            trades = [t for t in trades if t.get("broker_id") == broker_id]
        if symbol:
            trades = [t for t in trades if t["symbol"] == symbol]
        if side:
            trades = [t for t in trades if t["side"] == side]
        trades = _filter_by_regime(trades, trend_regime, volatility_regime, liquidity_regime)
        if not trades:
            continue
        summaries.append(asdict(compute_summary(trades)))

    def _sort_value(s: dict, key: str) -> float:
        v = s.get(key)
        if v is None:
            return float("-inf")
        return float(v)

    summaries.sort(key=lambda s: _sort_value(s, sort), reverse=True)
    return summaries[:limit]


@router.get("/{agent_name}")
async def get_strategy_drilldown(
    request: Request,
    agent_name: str,
    window: str = Query("all", pattern="^(7d|30d|90d|all)$"),
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    ws = _window_start(window)
    trades = await store.list_by_strategy(agent_name, window_start=ws, limit=10_000)

    summary = compute_summary(trades)
    eq_curve = compute_equity_curve(trades, cap=500)
    re_20 = compute_rolling_expectancy(trades, window=20)
    re_50 = compute_rolling_expectancy(trades, window=50)
    sym_breakdown = compute_symbol_breakdown(trades)

    sym_sorted = sorted(sym_breakdown, key=lambda s: float(s.net_pnl), reverse=True)
    top_symbols = sym_sorted[:5]
    bottom_symbols = sym_sorted[-5:] if len(sym_sorted) > 5 else []

    exit_reasons = compute_exit_reason_breakdown(trades)

    drilldown = StrategyDrilldown(
        summary=summary,
        equity_curve=eq_curve,
        rolling_expectancy_20=re_20,
        rolling_expectancy_50=re_50,
        top_symbols=top_symbols,
        bottom_symbols=bottom_symbols,
        exit_reasons=exit_reasons,
    )
    return asdict(drilldown)


@router.get("/{agent_name}/trades")
async def get_strategy_trades(
    request: Request,
    agent_name: str,
    window: str = Query("all", pattern="^(7d|30d|90d|all)$"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    ws = _window_start(window)
    trades = await store.list_by_strategy(agent_name, window_start=ws, limit=limit + offset)
    return trades[offset : offset + limit]


@router.get("/{agent_name}/symbols")
async def get_strategy_symbols(
    request: Request,
    agent_name: str,
    window: str = Query("all", pattern="^(7d|30d|90d|all)$"),
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    ws = _window_start(window)
    trades = await store.list_by_strategy(agent_name, window_start=ws, limit=10_000)
    breakdown = compute_symbol_breakdown(trades)
    return [asdict(b) for b in breakdown]
