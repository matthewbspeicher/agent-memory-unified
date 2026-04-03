from __future__ import annotations

import aiosqlite
import pytest

from storage.db import init_db
from storage.trade_analytics import TradeAnalyticsStore


@pytest.fixture
async def analytics_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield TradeAnalyticsStore(db)
    await db.close()


def _make_row(tracked_position_id: int = 1, **overrides) -> dict:
    defaults = {
        "opportunity_id": "opp-001",
        "agent_name": "rsi_agent",
        "signal": "buy",
        "symbol": "AAPL",
        "side": "long",
        "broker_id": "ib",
        "account_id": "U123",
        "entry_time": "2026-03-25T10:00:00",
        "exit_time": "2026-03-25T14:00:00",
        "hold_minutes": 240.0,
        "entry_price": "150.00",
        "exit_price": "155.00",
        "entry_quantity": 100,
        "entry_fees": "1.00",
        "exit_fees": "1.00",
        "gross_pnl": "500.00",
        "net_pnl": "498.00",
        "gross_return_pct": 0.0333,
        "net_return_pct": 0.0332,
        "realized_outcome": "win",
        "exit_reason": "profit_target",
        "confidence": 0.85,
    }
    defaults.update(overrides)
    return defaults


class TestTradeAnalyticsStore:
    async def test_upsert_and_get(self, analytics_store: TradeAnalyticsStore):
        row = _make_row(tracked_position_id=1)
        await analytics_store.upsert(tracked_position_id=1, **row)

        result = await analytics_store.get(1)
        assert result is not None
        assert result["tracked_position_id"] == 1
        assert result["agent_name"] == "rsi_agent"
        assert result["symbol"] == "AAPL"
        assert result["net_pnl"] == "498.00"
        assert result["realized_outcome"] == "win"

    async def test_upsert_idempotency(self, analytics_store: TradeAnalyticsStore):
        row = _make_row(tracked_position_id=42)
        await analytics_store.upsert(tracked_position_id=42, **row)

        updated_row = _make_row(tracked_position_id=42, net_pnl="600.00", realized_outcome="win")
        await analytics_store.upsert(tracked_position_id=42, **updated_row)

        # Should still be 1 row
        all_rows = await analytics_store.list_all()
        assert len(all_rows) == 1

        result = await analytics_store.get(42)
        assert result is not None
        assert result["net_pnl"] == "600.00"

    async def test_list_by_strategy(self, analytics_store: TradeAnalyticsStore):
        await analytics_store.upsert(
            tracked_position_id=1,
            **_make_row(agent_name="rsi_agent", exit_time="2026-03-25T14:00:00"),
        )
        await analytics_store.upsert(
            tracked_position_id=2,
            **_make_row(agent_name="macd_agent", exit_time="2026-03-25T15:00:00"),
        )
        await analytics_store.upsert(
            tracked_position_id=3,
            **_make_row(agent_name="rsi_agent", exit_time="2026-03-25T16:00:00"),
        )

        rsi_rows = await analytics_store.list_by_strategy("rsi_agent")
        assert len(rsi_rows) == 2
        assert all(r["agent_name"] == "rsi_agent" for r in rsi_rows)
        # Verify DESC ordering
        assert rsi_rows[0]["exit_time"] >= rsi_rows[1]["exit_time"]

    async def test_list_by_symbol(self, analytics_store: TradeAnalyticsStore):
        await analytics_store.upsert(
            tracked_position_id=1,
            **_make_row(symbol="AAPL", agent_name="rsi_agent"),
        )
        await analytics_store.upsert(
            tracked_position_id=2,
            **_make_row(symbol="TSLA", agent_name="rsi_agent"),
        )
        await analytics_store.upsert(
            tracked_position_id=3,
            **_make_row(symbol="AAPL", agent_name="macd_agent"),
        )

        aapl_rows = await analytics_store.list_by_symbol("AAPL")
        assert len(aapl_rows) == 2
        assert all(r["symbol"] == "AAPL" for r in aapl_rows)

        aapl_rsi = await analytics_store.list_by_symbol("AAPL", "rsi_agent")
        assert len(aapl_rsi) == 1
        assert aapl_rsi[0]["agent_name"] == "rsi_agent"

    async def test_list_all_with_window(self, analytics_store: TradeAnalyticsStore):
        await analytics_store.upsert(
            tracked_position_id=1,
            **_make_row(exit_time="2026-03-20T10:00:00"),
        )
        await analytics_store.upsert(
            tracked_position_id=2,
            **_make_row(exit_time="2026-03-25T10:00:00"),
        )
        await analytics_store.upsert(
            tracked_position_id=3,
            **_make_row(exit_time="2026-03-28T10:00:00"),
        )

        all_rows = await analytics_store.list_all()
        assert len(all_rows) == 3

        windowed = await analytics_store.list_all(window_start="2026-03-24T00:00:00")
        assert len(windowed) == 2
        assert all(r["exit_time"] >= "2026-03-24T00:00:00" for r in windowed)

    async def test_get_distinct_strategies(self, analytics_store: TradeAnalyticsStore):
        await analytics_store.upsert(
            tracked_position_id=1,
            **_make_row(agent_name="rsi_agent"),
        )
        await analytics_store.upsert(
            tracked_position_id=2,
            **_make_row(agent_name="macd_agent"),
        )
        await analytics_store.upsert(
            tracked_position_id=3,
            **_make_row(agent_name="rsi_agent"),
        )

        strategies = await analytics_store.get_distinct_strategies()
        assert strategies == ["macd_agent", "rsi_agent"]

    async def test_get_nonexistent(self, analytics_store: TradeAnalyticsStore):
        result = await analytics_store.get(999)
        assert result is None
