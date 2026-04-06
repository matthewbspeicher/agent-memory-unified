"""Integration tests for api/routes/backtest.py."""

from __future__ import annotations

import os
import pytest
import aiosqlite
from unittest.mock import MagicMock
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from api.auth import verify_api_key
from api.routes.backtest import router as backtest_router
from api.deps import get_agent_runner
from storage.db import init_db


_INSERT = """
    INSERT INTO backtest_results
        (agent_name, parameters, sharpe_ratio, profit_factor, total_pnl,
         max_drawdown, win_rate, total_trades, run_date, data_start, data_end)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_ROW_A = (
    "agent_a",
    "{}",
    1.5,
    1.2,
    "500.00",
    0.1,
    0.6,
    10,
    "2026-01-01T00:00:00",
    "2025-07-01",
    "2025-12-31",
)

_ROW_B = (
    "agent_b",
    "{}",
    0.8,
    0.9,
    "-200.00",
    0.2,
    0.4,
    5,
    "2026-01-02T00:00:00",
    "2025-07-01",
    "2025-12-31",
)


@pytest.fixture
async def app_and_db():
    """Async fixture: in-memory SQLite db with schema, minimal FastAPI app."""
    os.environ.setdefault("STA_API_KEY", "test-key")

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)

    app = FastAPI()
    app.state.db = db

    # Bypass auth
    app.dependency_overrides[verify_api_key] = lambda: "test-key"

    # Mock agent runner (no real agents) so the dependency resolves
    runner = MagicMock()
    runner._agents = {}
    app.dependency_overrides[get_agent_runner] = lambda: runner

    app.include_router(backtest_router)

    yield app, db

    await db.close()


@pytest.fixture
async def client(app_and_db):
    app, db = app_and_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_backtest_results_empty(client):
    c, _ = client
    resp = await c.get("/backtest/results")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_backtest_results_with_data(client):
    c, db = client
    await db.execute(_INSERT, _ROW_A)
    await db.commit()

    resp = await c.get("/backtest/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["agent_name"] == "agent_a"
    assert data[0]["total_trades"] == 10


@pytest.mark.asyncio
async def test_list_backtest_results_filtered_by_agent(client):
    c, db = client
    await db.execute(_INSERT, _ROW_A)
    await db.execute(_INSERT, _ROW_B)
    await db.commit()

    resp = await c.get("/backtest/results?agent_name=agent_a")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["agent_name"] == "agent_a"


@pytest.mark.asyncio
async def test_run_backtest_agent_not_found(client):
    c, _ = client
    resp = await c.post("/backtest", json={"agent_name": "nonexistent"})
    assert resp.status_code == 404
    assert "nonexistent" in resp.json()["detail"]
