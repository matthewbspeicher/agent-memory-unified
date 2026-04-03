"""Tests for ExecutionTracker — TDD phase."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from execution.tracker import ExecutionTracker, ExecutionFill


class TestExecutionFill:
    def test_positive_slippage_buy(self):
        """Buy filled above expected = positive slippage (worse)."""
        fill = ExecutionFill(
            opportunity_id="opp-1",
            agent_name="test_agent",
            broker_id="ibkr",
            symbol="AAPL",
            side="BUY",
            expected_price=Decimal("150.00"),
            actual_price=Decimal("150.30"),
            quantity=Decimal("10"),
        )
        assert fill.slippage_bps > 0
        assert abs(fill.slippage_bps - 20) < 1  # 0.30/150 * 10000 = 20 bps

    def test_negative_slippage_buy(self):
        """Buy filled below expected = negative slippage (better)."""
        fill = ExecutionFill(
            opportunity_id="opp-1",
            agent_name="test_agent",
            broker_id="ibkr",
            symbol="AAPL",
            side="BUY",
            expected_price=Decimal("150.00"),
            actual_price=Decimal("149.85"),
            quantity=Decimal("10"),
        )
        assert fill.slippage_bps < 0

    def test_zero_slippage(self):
        fill = ExecutionFill(
            opportunity_id="opp-1",
            agent_name="test_agent",
            broker_id="ibkr",
            symbol="AAPL",
            side="BUY",
            expected_price=Decimal("100.00"),
            actual_price=Decimal("100.00"),
            quantity=Decimal("5"),
        )
        assert fill.slippage_bps == 0.0

    def test_slippage_sell_inverted(self):
        """Sell filled below expected = positive slippage (worse for seller)."""
        fill = ExecutionFill(
            opportunity_id="opp-1",
            agent_name="test_agent",
            broker_id="ibkr",
            symbol="AAPL",
            side="SELL",
            expected_price=Decimal("150.00"),
            actual_price=Decimal("149.70"),
            quantity=Decimal("10"),
        )
        assert fill.slippage_bps > 0

    def test_zero_expected_price_safe(self):
        """Zero expected price should not crash."""
        fill = ExecutionFill(
            opportunity_id="opp-1",
            agent_name="test_agent",
            broker_id="ibkr",
            symbol="AAPL",
            side="BUY",
            expected_price=Decimal("0"),
            actual_price=Decimal("100.00"),
            quantity=Decimal("10"),
        )
        assert fill.slippage_bps == 0.0


class TestExecutionTracker:
    async def test_record_fill_saves_to_store(self):
        store = MagicMock()
        store.save = AsyncMock()
        tracker = ExecutionTracker(store=store)

        await tracker.record_fill(
            opportunity_id="opp-1",
            agent_name="test_agent",
            broker_id="ibkr",
            expected_price=Decimal("100.00"),
            actual_price=Decimal("100.10"),
            quantity=Decimal("10"),
            side="BUY",
            symbol="AAPL",
        )

        store.save.assert_awaited_once()
        call_args = store.save.call_args[0][0]
        assert isinstance(call_args, ExecutionFill)
        assert call_args.symbol == "AAPL"

    async def test_record_fill_no_store_does_not_crash(self):
        tracker = ExecutionTracker(store=None)
        # Should not raise
        await tracker.record_fill(
            opportunity_id="opp-1",
            agent_name="test_agent",
            broker_id="ibkr",
            expected_price=Decimal("100.00"),
            actual_price=Decimal("100.10"),
            quantity=Decimal("10"),
            side="BUY",
            symbol="AAPL",
        )

    async def test_record_fill_tracks_in_memory(self):
        tracker = ExecutionTracker(store=None)

        await tracker.record_fill(
            opportunity_id="opp-1",
            agent_name="alpha",
            broker_id="ibkr",
            expected_price=Decimal("200.00"),
            actual_price=Decimal("200.40"),
            quantity=Decimal("5"),
            side="BUY",
            symbol="TSLA",
        )
        await tracker.record_fill(
            opportunity_id="opp-2",
            agent_name="alpha",
            broker_id="ibkr",
            expected_price=Decimal("200.00"),
            actual_price=Decimal("200.20"),
            quantity=Decimal("5"),
            side="BUY",
            symbol="TSLA",
        )

        fills = tracker.get_fills("alpha")
        assert len(fills) == 2

    async def test_average_slippage_bps(self):
        tracker = ExecutionTracker(store=None)

        await tracker.record_fill(
            opportunity_id="opp-1",
            agent_name="alpha",
            broker_id="ibkr",
            expected_price=Decimal("100.00"),
            actual_price=Decimal("100.20"),  # 20 bps
            quantity=Decimal("10"),
            side="BUY",
            symbol="AAPL",
        )
        await tracker.record_fill(
            opportunity_id="opp-2",
            agent_name="alpha",
            broker_id="ibkr",
            expected_price=Decimal("100.00"),
            actual_price=Decimal("100.40"),  # 40 bps
            quantity=Decimal("10"),
            side="BUY",
            symbol="AAPL",
        )

        avg = tracker.average_slippage_bps("alpha")
        assert abs(avg - 30.0) < 1  # Average of 20 and 40 = 30 bps
