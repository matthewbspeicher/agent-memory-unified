"""Tests for StrategyHealthStore persistence."""

from __future__ import annotations

import aiosqlite
import pytest

from storage.db import init_db
from storage.strategy_health import StrategyHealthStore


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield StrategyHealthStore(db)
    await db.close()


class TestStrategyHealthStore:
    async def test_get_status_returns_none_when_missing(self, store):
        result = await store.get_status("unknown_agent")
        assert result is None

    async def test_upsert_and_get_status(self, store):
        await store.upsert_status("rsi_agent", "normal")
        row = await store.get_status("rsi_agent")
        assert row is not None
        assert row["status"] == "normal"
        assert row["agent_name"] == "rsi_agent"

    async def test_upsert_updates_existing_row(self, store):
        await store.upsert_status("rsi_agent", "normal")
        await store.upsert_status(
            "rsi_agent", "watchlist", trigger_reason="bad expectancy"
        )
        row = await store.get_status("rsi_agent")
        assert row["status"] == "watchlist"
        assert row["trigger_reason"] == "bad expectancy"

    async def test_upsert_stores_all_fields(self, store):
        await store.upsert_status(
            "rsi_agent",
            "throttled",
            health_score=0.4,
            rolling_expectancy="-0.005",
            rolling_drawdown="-6000",
            rolling_win_rate=0.38,
            rolling_trade_count=55,
            throttle_multiplier=0.5,
            trigger_reason="drawdown breach",
        )
        row = await store.get_status("rsi_agent")
        assert row["status"] == "throttled"
        assert row["rolling_trade_count"] == 55
        assert float(row["throttle_multiplier"]) == pytest.approx(0.5)
        assert row["trigger_reason"] == "drawdown breach"

    async def test_get_all_statuses_empty(self, store):
        rows = await store.get_all_statuses()
        assert rows == []

    async def test_get_all_statuses_multiple_agents(self, store):
        await store.upsert_status("agent_a", "normal")
        await store.upsert_status("agent_b", "watchlist")
        rows = await store.get_all_statuses()
        assert len(rows) == 2
        names = {r["agent_name"] for r in rows}
        assert names == {"agent_a", "agent_b"}

    async def test_record_event_and_get_events(self, store):
        await store.record_event(
            agent_name="rsi_agent",
            old_status="normal",
            new_status="watchlist",
            reason="expectancy below floor",
            metrics_snapshot={"expectancy": -0.001, "win_rate": 0.4},
            actor="system",
        )
        events = await store.get_events("rsi_agent", limit=10)
        assert len(events) == 1
        ev = events[0]
        assert ev["old_status"] == "normal"
        assert ev["new_status"] == "watchlist"
        assert ev["actor"] == "system"
        assert ev["metrics_snapshot"]["expectancy"] == pytest.approx(-0.001)

    async def test_get_events_returns_newest_first(self, store):
        for reason in ("first", "second", "third"):
            await store.record_event(
                "rsi_agent",
                "normal",
                "watchlist",
                reason=reason,
                metrics_snapshot={},
                actor="system",
            )
        events = await store.get_events("rsi_agent", limit=10)
        # newest first — third was inserted last
        assert events[0]["reason"] == "third"

    async def test_get_events_respects_limit(self, store):
        for i in range(5):
            await store.record_event(
                "rsi_agent",
                None,
                "normal",
                reason=f"event-{i}",
                metrics_snapshot={},
                actor="system",
            )
        events = await store.get_events("rsi_agent", limit=3)
        assert len(events) == 3

    async def test_get_events_empty_for_unknown_agent(self, store):
        events = await store.get_events("nobody", limit=10)
        assert events == []

    async def test_set_override_creates_upsert_and_event(self, store):
        await store.set_override(
            "rsi_agent", "retired", actor="operator", reason="manual retire"
        )
        row = await store.get_status("rsi_agent")
        assert row["status"] == "retired"
        assert row["manual_override"] == "operator"

        events = await store.get_events("rsi_agent", limit=5)
        assert len(events) == 1
        assert events[0]["actor"] == "operator"
        assert events[0]["new_status"] == "retired"

    async def test_set_override_records_old_status(self, store):
        await store.upsert_status("rsi_agent", "throttled")
        await store.set_override("rsi_agent", "normal", actor="operator")
        events = await store.get_events("rsi_agent", limit=5)
        assert events[0]["old_status"] == "throttled"
        assert events[0]["new_status"] == "normal"
