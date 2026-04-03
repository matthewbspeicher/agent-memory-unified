"""Execution analytics API routes — summary, trades, worst groups."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request

from analytics.execution_costs import compute_grouped_summary, compute_worst_groups
from api.auth import verify_api_key
from storage.execution_costs import ExecutionCostStore

router = APIRouter(prefix="/analytics/execution-costs", tags=["execution-analytics"])

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


def _get_store(request: Request) -> ExecutionCostStore:
    return ExecutionCostStore(request.app.state.db)


@router.get("/summary")
async def get_summary(
    request: Request,
    window: str = Query("all", pattern="^(7d|30d|90d|all)$"),
    broker_id: str | None = None,
    symbol: str | None = None,
    agent_name: str | None = None,
    order_type: str | None = None,
    group_by: str = Query("broker_id", pattern="^(broker_id|symbol|agent_name|order_type)$"),
    _: str = Depends(verify_api_key),
):
    """Aggregated execution cost summary grouped by one dimension."""
    store = _get_store(request)
    ws = _window_start(window)
    rows = await store.list_events(
        broker_id=broker_id,
        symbol=symbol,
        agent_name=agent_name,
        order_type=order_type,
        window_start=ws,
        limit=10_000,
    )
    return compute_grouped_summary(rows, group_by)


@router.get("/trades")
async def get_trades(
    request: Request,
    window: str = Query("all", pattern="^(7d|30d|90d|all)$"),
    broker_id: str | None = None,
    symbol: str | None = None,
    agent_name: str | None = None,
    order_type: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: str = Depends(verify_api_key),
):
    """Per-trade execution cost attribution rows."""
    store = _get_store(request)
    ws = _window_start(window)
    rows = await store.list_events(
        broker_id=broker_id,
        symbol=symbol,
        agent_name=agent_name,
        order_type=order_type,
        window_start=ws,
        limit=limit + offset,
    )
    return rows[offset : offset + limit]


@router.get("/worst")
async def get_worst(
    request: Request,
    window: str = Query("all", pattern="^(7d|30d|90d|all)$"),
    group_by: str = Query("symbol", pattern="^(broker_id|symbol|agent_name|order_type)$"),
    limit: int = Query(10, ge=1, le=50),
    _: str = Depends(verify_api_key),
):
    """Worst-performing groups by average execution slippage."""
    store = _get_store(request)
    ws = _window_start(window)
    rows = await store.list_events(window_start=ws, limit=10_000)
    return compute_worst_groups(rows, group_by, limit=limit)
