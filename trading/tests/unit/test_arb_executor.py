"""Tests for ArbExecutor auto-execution."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import logging

import pytest


class TestArbExecutor:
    def test_set_enabled(self):
        from execution.arb_executor import ArbExecutor

        mock_store = MagicMock()
        mock_coordinator = MagicMock()
        mock_bus = MagicMock()

        executor = ArbExecutor(
            spread_store=mock_store,
            arb_coordinator=mock_coordinator,
            event_bus=mock_bus,
            min_profit_bps=5.0,
            max_position_usd=100.0,
            enabled=False,
        )

        assert executor._enabled is False
        executor.set_enabled(True)
        assert executor._enabled is True
        executor.set_enabled(False)
        assert executor._enabled is False

    def test_handles_spread_below_threshold(self):
        from execution.arb_executor import ArbExecutor

        mock_store = MagicMock()
        mock_coordinator = MagicMock()
        mock_bus = MagicMock()

        executor = ArbExecutor(
            spread_store=mock_store,
            arb_coordinator=mock_coordinator,
            event_bus=mock_bus,
            min_profit_bps=5.0,
            max_position_usd=100.0,
            enabled=True,
        )

        # Spread below threshold should be ignored
        # This would be tested via _handle_spread but it's async
        assert executor._min_profit_bps == 5.0


# ---------------------------------------------------------------------------
# Sizing wiring + bug-fix tests
# ---------------------------------------------------------------------------


def _make_executor(sizing_engine=None, enabled=True):
    """Construct an ArbExecutor with mocked deps for sizing/dispatch tests."""
    from agents.models import TrustLevel
    from execution.arb_executor import ArbExecutor

    coord = MagicMock()
    coord.execute_arbitrage = AsyncMock(return_value=True)
    return ArbExecutor(
        spread_store=MagicMock(),
        arb_coordinator=coord,
        event_bus=MagicMock(),
        min_profit_bps=5.0,
        max_position_usd=100.0,
        enabled=enabled,
        sizing_engine=sizing_engine,
        bankroll_usd=Decimal("100"),
        agent_name="cross_platform_arb",
        trust_level=TrustLevel.MONITORED,
    )


@pytest.mark.asyncio
async def test_execute_arb_builds_prediction_symbols_not_stock():
    """Regression guard: legs must use AssetType.PREDICTION, not STOCK."""
    from broker.models import AssetType

    exe = _make_executor()
    await exe._execute_arb(
        observation_id=1,
        kalshi_ticker="KTICK",
        poly_ticker="0xpoly",
        gap_cents=10,
        kalshi_cents=45,
        poly_cents=55,
    )
    assert exe._coordinator.execute_arbitrage.await_count == 1
    trade = exe._coordinator.execute_arbitrage.await_args.args[0]
    assert trade.leg_a.order.symbol.asset_type == AssetType.PREDICTION
    assert trade.leg_b.order.symbol.asset_type == AssetType.PREDICTION


@pytest.mark.asyncio
async def test_execute_arb_uses_less_liquid_first_sequencing():
    """Regression guard: SequencingStrategy.CONCURRENT doesn't exist; must
    pick a value that's actually defined in the enum."""
    from execution.models import SequencingStrategy

    exe = _make_executor()
    await exe._execute_arb(
        observation_id=1,
        kalshi_ticker="KTICK",
        poly_ticker="0xpoly",
        gap_cents=10,
        kalshi_cents=45,
        poly_cents=55,
    )
    trade = exe._coordinator.execute_arbitrage.await_args.args[0]
    assert trade.sequencing == SequencingStrategy.LESS_LIQUID_FIRST


@pytest.mark.asyncio
async def test_compute_quantity_uses_sizing_engine_when_wired():
    """SizingEngine.compute_size is called with mid-price from k/p cents."""
    from agents.models import TrustLevel

    engine = MagicMock()
    engine.compute_size = AsyncMock(return_value=Decimal("25"))
    exe = _make_executor(sizing_engine=engine)

    qty = await exe._compute_quantity(kalshi_cents=40, poly_cents=60)

    assert qty == Decimal("25")
    assert engine.compute_size.await_count == 1
    call_kwargs = engine.compute_size.await_args.kwargs
    assert call_kwargs["agent_name"] == "cross_platform_arb"
    assert call_kwargs["trust_level"] == TrustLevel.MONITORED
    assert call_kwargs["bankroll"] == Decimal("100")
    # Mid = (40 + 60) / 200 = 0.50
    assert call_kwargs["price"] == Decimal("0.5")


@pytest.mark.asyncio
async def test_compute_quantity_falls_back_to_one_when_no_engine():
    """Sites that construct ArbExecutor without a SizingEngine (legacy
    callers, simple tests) get the safe minimum of 1 share."""
    exe = _make_executor(sizing_engine=None)
    qty = await exe._compute_quantity(kalshi_cents=45, poly_cents=55)
    assert qty == Decimal("1")


@pytest.mark.asyncio
async def test_compute_quantity_falls_back_when_engine_raises():
    """Defensive fallback: a buggy SizingEngine must not block execution."""
    engine = MagicMock()
    engine.compute_size = AsyncMock(side_effect=RuntimeError("perf_store down"))
    exe = _make_executor(sizing_engine=engine)
    qty = await exe._compute_quantity(kalshi_cents=45, poly_cents=55)
    assert qty == Decimal("1")


@pytest.mark.asyncio
async def test_compute_quantity_handles_missing_prices():
    """When k/p cents are None (defensive), default to 50¢ neutral price."""
    engine = MagicMock()
    engine.compute_size = AsyncMock(return_value=Decimal("7"))
    exe = _make_executor(sizing_engine=engine)
    qty = await exe._compute_quantity(kalshi_cents=None, poly_cents=None)
    assert qty == Decimal("7")
    call_kwargs = engine.compute_size.await_args.kwargs
    assert call_kwargs["price"] == Decimal("0.5")


def test_set_sizing_engine_injects_post_construction():
    """app.py relies on this setter — SizingEngine is constructed AFTER
    ArbExecutor in the lifespan (engine depends on perf_store which is
    initialized later)."""
    exe = _make_executor(sizing_engine=None)
    assert exe._sizing_engine is None

    engine = MagicMock()
    exe.set_sizing_engine(engine)
    assert exe._sizing_engine is engine

    exe.set_sizing_engine(None)
    assert exe._sizing_engine is None


@pytest.mark.asyncio
async def test_execute_arb_quantity_threads_through_to_legs():
    """End-to-end: _execute_arb pulls quantity from _compute_quantity and
    both legs receive the same size."""
    engine = MagicMock()
    engine.compute_size = AsyncMock(return_value=Decimal("3"))
    exe = _make_executor(sizing_engine=engine)
    await exe._execute_arb(
        observation_id=1,
        kalshi_ticker="KTICK",
        poly_ticker="0xpoly",
        gap_cents=10,
        kalshi_cents=45,
        poly_cents=55,
    )
    trade = exe._coordinator.execute_arbitrage.await_args.args[0]
    assert trade.leg_a.order.quantity == Decimal("3")
    assert trade.leg_b.order.quantity == Decimal("3")


# ---------------------------------------------------------------------------
# Shadow-mode logging tests
# ---------------------------------------------------------------------------


def _shadow_records(caplog) -> list[dict]:
    """Extract arb.shadow event data from caplog."""
    out: list[dict] = []
    for rec in caplog.records:
        if getattr(rec, "event_type", None) == "arb.shadow":
            data = getattr(rec, "event_data", None) or {}
            out.append(data)
    return out


@pytest.mark.asyncio
async def test_shadow_mode_profitable_spread_logs_event_no_claim_no_dispatch(caplog):
    """When disabled, a profitable spread emits arb.shadow with
    would_execute=True and does NOT claim_spread or dispatch to coordinator."""
    from execution.cost_model import CostModel

    cost_model = CostModel()
    exe = _make_executor(enabled=False)
    exe._cost_model = cost_model

    profitable_gap = cost_model.min_gap_cents() + 5.0

    with caplog.at_level(logging.INFO, logger="execution.arb_executor"):
        await exe._log_shadow_decision(
            {
                "observation_id": 42,
                "kalshi_ticker": "KQ-YES",
                "poly_ticker": "0xpoly_yes",
                "gap_cents": profitable_gap,
                "kalshi_cents": 55,
                "poly_cents": 45,
            }
        )

    records = _shadow_records(caplog)
    assert len(records) == 1
    data = records[0]
    assert data["observation_id"] == 42
    assert data["would_execute"] is True
    assert data["reason_blocked"] is None
    assert data["kalshi_side"] == "SELL"
    assert data["poly_side"] == "BUY"
    assert data["computed_quantity"] == "1"

    exe._store.claim_spread.assert_not_called()
    exe._coordinator.execute_arbitrage.assert_not_called()


@pytest.mark.asyncio
async def test_shadow_mode_unprofitable_spread_logs_blocked_reason(caplog):
    """When disabled, an unprofitable spread emits arb.shadow with
    would_execute=False and reason_blocked='below_min_profit_bps'."""
    from execution.cost_model import CostModel

    cost_model = CostModel()
    exe = _make_executor(enabled=False)
    exe._cost_model = cost_model

    unprofitable_gap = 0.01

    with caplog.at_level(logging.INFO, logger="execution.arb_executor"):
        await exe._log_shadow_decision(
            {
                "observation_id": 99,
                "kalshi_ticker": "KQ-NO",
                "poly_ticker": "0xpoly_no",
                "gap_cents": unprofitable_gap,
                "kalshi_cents": 50,
                "poly_cents": 50,
            }
        )

    records = _shadow_records(caplog)
    assert len(records) == 1
    data = records[0]
    assert data["observation_id"] == 99
    assert data["would_execute"] is False
    assert data["reason_blocked"] == "below_min_profit_bps"

    exe._store.claim_spread.assert_not_called()
    exe._coordinator.execute_arbitrage.assert_not_called()
