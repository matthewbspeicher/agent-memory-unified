"""Tests for the agent_convergence SignalBus topic (ADR-0013).

Covers:
1. AgentConvergencePayload validates correctly (direction enum,
   confidence bounds, defaults).
2. The "agent_convergence" type is in the global registry.
3. WarRoomEngine publishes to the bus on detection when signal_bus is set.
4. WarRoomEngine works without signal_bus (back-compat).
5. Dedupe: a convergence with the same id is not published twice across
   multiple detect_convergences() calls.
6. Publish failures don't break detection (best-effort).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from data.signal_bus import SignalBus
from data.signal_types import AgentConvergencePayload, registry
from warroom.engine import WarRoomEngine


# ---------------------------------------------------------------------------
# 1-2. Payload + registration
# ---------------------------------------------------------------------------


class TestAgentConvergencePayload:
    def test_valid_minimal(self):
        payload = {
            "convergence_id": "abc123",
            "symbol": "AAPL",
            "direction": "BUY",
            "agents": ["buffett_value", "lynch_growth"],
            "opportunity_ids": ["o1", "o2"],
            "avg_confidence": 0.72,
            "first_seen": "2026-05-22T14:00:00+00:00",
        }
        m = AgentConvergencePayload.model_validate(payload)
        assert m.convergence_id == "abc123"
        assert m.direction == "BUY"
        assert m.avg_confidence == 0.72
        assert m.synthesis == ""

    def test_direction_enum_rejects_invalid(self):
        with pytest.raises(ValidationError):
            AgentConvergencePayload.model_validate(
                {
                    "convergence_id": "x",
                    "symbol": "AAPL",
                    "direction": "HOLD",  # not BUY/SELL
                    "agents": [],
                    "opportunity_ids": [],
                    "avg_confidence": 0.5,
                    "first_seen": "now",
                }
            )

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            AgentConvergencePayload.model_validate(
                {
                    "convergence_id": "x",
                    "symbol": "AAPL",
                    "direction": "BUY",
                    "agents": [],
                    "opportunity_ids": [],
                    "avg_confidence": 1.5,
                    "first_seen": "now",
                }
            )

    def test_registered_in_global_registry(self):
        assert "agent_convergence" in registry
        assert registry.get("agent_convergence") is AgentConvergencePayload


# ---------------------------------------------------------------------------
# 3-6. WarRoomEngine publishing
# ---------------------------------------------------------------------------


def _make_db_with_rows(rows: list[tuple]) -> MagicMock:
    """Mock aiosqlite Connection that returns *rows* from any execute()."""
    cursor = MagicMock()
    cursor.fetchall = AsyncMock(return_value=rows)
    cursor.fetchone = AsyncMock(return_value=None)
    db = MagicMock()
    db.execute = AsyncMock(return_value=cursor)
    db.commit = AsyncMock()
    return db


def _opp_row(
    *,
    opp_id: str,
    agent_name: str,
    symbol: str,
    signal: str,
    confidence: float = 0.7,
    created_at: str | None = None,
    reasoning: str = "",
) -> tuple:
    """Row shape matching the SELECT in detect_convergences."""
    return (
        opp_id,
        agent_name,
        symbol,
        signal,
        confidence,
        created_at or "2026-05-22T14:00:00",
        reasoning,
    )


class TestWarRoomPublishesConvergence:
    @pytest.mark.asyncio
    async def test_publishes_when_signal_bus_set(self):
        bus = SignalBus()
        db = _make_db_with_rows(
            [
                _opp_row(opp_id="o1", agent_name="buffett_value", symbol="AAPL", signal="BUY"),
                _opp_row(opp_id="o2", agent_name="lynch_growth", symbol="AAPL", signal="BUY"),
            ]
        )
        engine = WarRoomEngine(db=db, llm=MagicMock(), signal_bus=bus)

        convs = await engine.detect_convergences(hours=4)

        assert len(convs) == 1
        signals = bus.query(signal_type="agent_convergence")
        assert len(signals) == 1
        s = signals[0]
        assert s.source_agent == "warroom_engine"
        assert s.payload["symbol"] == "AAPL"
        assert s.payload["direction"] == "BUY"
        assert set(s.payload["agents"]) == {"buffett_value", "lynch_growth"}
        assert s.payload["convergence_id"] == convs[0].id

    @pytest.mark.asyncio
    async def test_does_not_publish_when_no_bus(self):
        """Back-compat: omitting signal_bus must not break detection."""
        db = _make_db_with_rows(
            [
                _opp_row(opp_id="o1", agent_name="a1", symbol="AAPL", signal="BUY"),
                _opp_row(opp_id="o2", agent_name="a2", symbol="AAPL", signal="BUY"),
            ]
        )
        engine = WarRoomEngine(db=db, llm=MagicMock())  # no signal_bus
        convs = await engine.detect_convergences(hours=4)
        assert len(convs) == 1
        # No bus → no failure, no publish.  Just smoke.

    @pytest.mark.asyncio
    async def test_dedupes_across_calls(self):
        """Calling detect_convergences twice must NOT republish the same id."""
        bus = SignalBus()
        db = _make_db_with_rows(
            [
                _opp_row(opp_id="o1", agent_name="a1", symbol="AAPL", signal="BUY"),
                _opp_row(opp_id="o2", agent_name="a2", symbol="AAPL", signal="BUY"),
            ]
        )
        engine = WarRoomEngine(db=db, llm=MagicMock(), signal_bus=bus)

        await engine.detect_convergences(hours=4)
        await engine.detect_convergences(hours=4)
        await engine.detect_convergences(hours=4)

        signals = bus.query(signal_type="agent_convergence")
        assert len(signals) == 1, (
            "convergence republished — dedupe broken"
        )

    @pytest.mark.asyncio
    async def test_new_convergence_publishes_after_existing(self):
        """A new (different) convergence still publishes alongside the cached one."""
        bus = SignalBus()
        # First call: AAPL convergence
        db1 = _make_db_with_rows(
            [
                _opp_row(opp_id="o1", agent_name="a1", symbol="AAPL", signal="BUY"),
                _opp_row(opp_id="o2", agent_name="a2", symbol="AAPL", signal="BUY"),
            ]
        )
        engine = WarRoomEngine(db=db1, llm=MagicMock(), signal_bus=bus)
        await engine.detect_convergences(hours=4)

        # Replace db with a new convergence
        engine._db = _make_db_with_rows(
            [
                _opp_row(opp_id="o3", agent_name="a3", symbol="MSFT", signal="SELL"),
                _opp_row(opp_id="o4", agent_name="a4", symbol="MSFT", signal="SELL"),
            ]
        )
        await engine.detect_convergences(hours=4)

        signals = bus.query(signal_type="agent_convergence")
        assert len(signals) == 2
        symbols = {s.payload["symbol"] for s in signals}
        assert symbols == {"AAPL", "MSFT"}

    @pytest.mark.asyncio
    async def test_below_threshold_does_not_publish(self):
        """Single-agent reports must NOT trigger convergence."""
        bus = SignalBus()
        db = _make_db_with_rows(
            [
                _opp_row(opp_id="o1", agent_name="solo", symbol="AAPL", signal="BUY"),
            ]
        )
        engine = WarRoomEngine(db=db, llm=MagicMock(), signal_bus=bus)
        convs = await engine.detect_convergences(hours=4)
        assert convs == []
        assert bus.query(signal_type="agent_convergence") == []

    @pytest.mark.asyncio
    async def test_publish_failure_does_not_break_detection(self):
        """A broken bus must not poison the convergence list returned to HTTP."""
        broken_bus = MagicMock()
        broken_bus.publish = AsyncMock(side_effect=RuntimeError("bus down"))
        db = _make_db_with_rows(
            [
                _opp_row(opp_id="o1", agent_name="a1", symbol="AAPL", signal="BUY"),
                _opp_row(opp_id="o2", agent_name="a2", symbol="AAPL", signal="BUY"),
            ]
        )
        engine = WarRoomEngine(db=db, llm=MagicMock(), signal_bus=broken_bus)

        # Must NOT raise.
        convs = await engine.detect_convergences(hours=4)
        assert len(convs) == 1, "detection broken by publish failure"

    @pytest.mark.asyncio
    async def test_dedupe_eviction_capped(self):
        """The dedupe set must be bounded — many distinct convergences
        eventually evict the oldest."""
        bus = SignalBus()
        engine = WarRoomEngine(db=MagicMock(), llm=MagicMock(), signal_bus=bus)
        # Drive the cap directly (faster than synthesizing 10k convergences).
        cap = engine._published_order.maxlen
        assert cap is not None
        # Fill to capacity
        for i in range(cap):
            engine._mark_published(f"id_{i}")
        assert len(engine._published_ids) == cap
        # One more → oldest must be evicted
        engine._mark_published("id_extra")
        assert "id_0" not in engine._published_ids
        assert "id_extra" in engine._published_ids
        assert len(engine._published_ids) == cap
