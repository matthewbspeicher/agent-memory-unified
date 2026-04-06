"""Tests for SlippageFeedbackLoop."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from agents.models import TrustLevel
from execution.feedback import SlippageFeedbackLoop
from execution.tracker import ExecutionFill, ExecutionTracker
from storage.agent_registry import AgentStore
from storage.performance import PerformanceSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fill(
    agent: str,
    slippage_bps: float,
    expected_price: float = 100.0,
    days_ago: int = 0,
) -> ExecutionFill:
    """Build an ExecutionFill with a precise target slippage_bps for BUY side."""
    expected = Decimal(str(expected_price))
    diff = Decimal(str(slippage_bps)) * expected / Decimal("10000")
    actual = expected + diff
    filled_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return ExecutionFill(
        opportunity_id="opp-test",
        agent_name=agent,
        broker_id="ibkr",
        symbol="AAPL",
        side="BUY",
        expected_price=expected,
        actual_price=actual,
        quantity=Decimal("10"),
        filled_at=filled_at,
    )


def _snapshot(agent: str, total_pnl: float, total_trades: int) -> PerformanceSnapshot:
    return PerformanceSnapshot(
        agent_name=agent,
        timestamp=datetime.now(timezone.utc),
        opportunities_generated=total_trades,
        opportunities_executed=total_trades,
        win_rate=0.5,
        total_pnl=Decimal(str(total_pnl)),
        total_trades=total_trades,
    )


def _make_loop(
    fills: list[ExecutionFill],
    override_row: dict | None,
    snapshot: PerformanceSnapshot | None,
    window: int = 20,
    consecutive_threshold: int = 3,
    min_fills: int = 10,
    max_days_lookback: int = 30,
) -> SlippageFeedbackLoop:
    """Build a SlippageFeedbackLoop with mocked dependencies."""
    tracker = MagicMock(spec=ExecutionTracker)
    tracker.get_recent_fills.return_value = fills

    perf_store = MagicMock()
    perf_store.get_latest = AsyncMock(return_value=snapshot)

    agent_store = MagicMock(spec=AgentStore)
    agent_store.get = AsyncMock(return_value=override_row)
    agent_store.update = AsyncMock()
    agent_store.log_trust_change = AsyncMock()

    return SlippageFeedbackLoop(
        tracker=tracker,
        perf_store=perf_store,
        agent_store=agent_store,
        window=window,
        consecutive_threshold=consecutive_threshold,
        min_fills=min_fills,
        max_days_lookback=max_days_lookback,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSlippageFeedbackLoop:
    @pytest.mark.asyncio
    async def test_downgrade_after_consecutive_breaches(self):
        """Slippage > edge for 3 consecutive checks → trust downgraded autonomous → assisted."""
        # 150 bps slippage, edge ≈ 100 bps  (total_pnl=10, trades=10, entry=100 → 100 bps)
        fills = [_fill("alpha", 150.0) for _ in range(15)]
        snapshot = _snapshot("alpha", total_pnl=10.0, total_trades=10)
        # current trust = AUTONOMOUS
        override_row = {"trust_level": TrustLevel.AUTONOMOUS.value}

        loop = _make_loop(
            fills=fills,
            override_row=override_row,
            snapshot=snapshot,
            consecutive_threshold=3,
            min_fills=10,
        )

        # First two checks don't yet meet threshold
        result1 = await loop.check_agent("alpha")
        assert result1 is None  # breach count = 1

        result2 = await loop.check_agent("alpha")
        assert result2 is None  # breach count = 2

        # Third check hits threshold
        result3 = await loop.check_agent("alpha")
        assert result3 is not None
        action, new_trust = result3
        assert action == "downgrade"
        assert new_trust == TrustLevel.ASSISTED

    @pytest.mark.asyncio
    async def test_no_downgrade_breach_resets_before_threshold(self):
        """Slippage > edge for 2 checks then improves → breach counter resets, no downgrade."""
        bad_fills = [_fill("beta", 150.0) for _ in range(15)]
        good_fills = [_fill("beta", 2.0) for _ in range(15)]

        snapshot = _snapshot("beta", total_pnl=10.0, total_trades=10)
        override_row = {"trust_level": TrustLevel.AUTONOMOUS.value}

        loop = _make_loop(
            fills=bad_fills,
            override_row=override_row,
            snapshot=snapshot,
            consecutive_threshold=3,
            min_fills=10,
        )

        # Two breaches
        await loop.check_agent("beta")
        await loop.check_agent("beta")
        assert loop._consecutive_breach.get("beta", 0) == 2

        # Swap to good fills — slippage is now within edge
        loop._tracker.get_recent_fills.return_value = good_fills

        result = await loop.check_agent("beta")
        # Counter resets; no downgrade action
        assert loop._consecutive_breach.get("beta", 0) == 0
        # Recovery returns None (agent was never downgraded so no ceiling set)
        assert result is None

    @pytest.mark.asyncio
    async def test_already_at_monitored_no_further_downgrade(self):
        """Agent already at MONITORED → check returns None (cannot go lower)."""
        fills = [_fill("gamma", 200.0) for _ in range(15)]
        snapshot = _snapshot("gamma", total_pnl=5.0, total_trades=10)
        override_row = {"trust_level": TrustLevel.MONITORED.value}

        loop = _make_loop(
            fills=fills,
            override_row=override_row,
            snapshot=snapshot,
            consecutive_threshold=1,
            min_fills=10,
        )

        result = await loop.check_agent("gamma")
        assert result is None

    @pytest.mark.asyncio
    async def test_recovery_after_improvement(self):
        """After downgrade, slippage improving → trust upgraded one notch."""
        bad_fills = [_fill("delta", 200.0) for _ in range(15)]
        good_fills = [_fill("delta", 1.0) for _ in range(15)]

        snapshot = _snapshot("delta", total_pnl=10.0, total_trades=10)

        # Start at AUTONOMOUS; mock agent_store to track writes
        current_trust = [TrustLevel.AUTONOMOUS]

        async def mock_get(agent_name):
            return {"trust_level": current_trust[0].value}

        async def mock_update(agent_name, **kwargs):
            if "trust_level" in kwargs:
                current_trust[0] = TrustLevel(kwargs["trust_level"])

        tracker = MagicMock(spec=ExecutionTracker)
        tracker.get_recent_fills.return_value = bad_fills
        perf_store = MagicMock()
        perf_store.get_latest = AsyncMock(return_value=snapshot)
        agent_store = MagicMock(spec=AgentStore)
        agent_store.get = AsyncMock(side_effect=mock_get)
        agent_store.update = AsyncMock(side_effect=mock_update)
        agent_store.log_trust_change = AsyncMock()

        loop = SlippageFeedbackLoop(
            tracker=tracker,
            perf_store=perf_store,
            agent_store=agent_store,
            consecutive_threshold=3,
            min_fills=10,
        )

        # Trigger 3 consecutive breaches → downgrade to ASSISTED
        await loop.check_agent("delta")
        await loop.check_agent("delta")
        downgrade_result = await loop.check_agent("delta")
        assert downgrade_result == ("downgrade", TrustLevel.ASSISTED)
        assert current_trust[0] == TrustLevel.ASSISTED

        # Now slippage improves
        tracker.get_recent_fills.return_value = good_fills
        loop._consecutive_breach["delta"] = 0

        recovery_result = await loop.check_agent("delta")
        assert recovery_result is not None
        action, new_trust = recovery_result
        assert action == "recovery"
        assert new_trust == TrustLevel.AUTONOMOUS  # back to original ceiling

    @pytest.mark.asyncio
    async def test_recovery_caps_at_original_trust_ceiling(self):
        """Recovery never exceeds the trust level the agent had before downgrade."""
        # Agent was at ASSISTED before downgrade — ceiling is ASSISTED
        current_trust = [TrustLevel.MONITORED]

        async def mock_get(agent_name):
            return {"trust_level": current_trust[0].value}

        async def mock_update(agent_name, **kwargs):
            if "trust_level" in kwargs:
                current_trust[0] = TrustLevel(kwargs["trust_level"])

        good_fills = [_fill("epsilon", 1.0) for _ in range(15)]
        snapshot = _snapshot("epsilon", total_pnl=10.0, total_trades=10)

        tracker = MagicMock(spec=ExecutionTracker)
        tracker.get_recent_fills.return_value = good_fills
        perf_store = MagicMock()
        perf_store.get_latest = AsyncMock(return_value=snapshot)
        agent_store = MagicMock(spec=AgentStore)
        agent_store.get = AsyncMock(side_effect=mock_get)
        agent_store.update = AsyncMock(side_effect=mock_update)
        agent_store.log_trust_change = AsyncMock()

        loop = SlippageFeedbackLoop(
            tracker=tracker,
            perf_store=perf_store,
            agent_store=agent_store,
            consecutive_threshold=3,
            min_fills=10,
        )

        # Manually seed state: original trust was ASSISTED, current is MONITORED
        loop._original_trust["epsilon"] = TrustLevel.ASSISTED

        recovery_result = await loop.check_agent("epsilon")
        assert recovery_result is not None
        action, new_trust = recovery_result
        assert action == "recovery"
        # Should only go up to ASSISTED (the ceiling), not AUTONOMOUS
        assert new_trust == TrustLevel.ASSISTED
        assert current_trust[0] == TrustLevel.ASSISTED

    @pytest.mark.asyncio
    async def test_not_enough_fills_no_action(self):
        """Fewer than min_fills → check_agent returns None immediately."""
        fills = [_fill("zeta", 200.0) for _ in range(5)]  # only 5 fills
        snapshot = _snapshot("zeta", total_pnl=10.0, total_trades=10)
        override_row = {"trust_level": TrustLevel.AUTONOMOUS.value}

        loop = _make_loop(
            fills=fills,
            override_row=override_row,
            snapshot=snapshot,
            min_fills=10,
        )

        result = await loop.check_agent("zeta")
        assert result is None

    @pytest.mark.asyncio
    async def test_fills_older_than_max_days_excluded(self):
        """Fills beyond max_days_lookback are excluded from the window."""
        tracker = ExecutionTracker(store=None)
        agent = "eta"

        # Add 15 fresh fills (slippage ~100 bps)
        expected = Decimal("100.00")
        actual_high = expected + expected * Decimal("100") / Decimal("10000")
        for i in range(15):
            fill = ExecutionFill(
                opportunity_id=f"opp-{i}",
                agent_name=agent,
                broker_id="ibkr",
                symbol="AAPL",
                side="BUY",
                expected_price=expected,
                actual_price=actual_high,
                quantity=Decimal("10"),
                filled_at=datetime.now(timezone.utc)
                - timedelta(days=1),  # 1 day ago — fresh
            )
            tracker._fills.setdefault(agent, []).append(fill)

        # Add 10 stale fills (40 days ago — beyond 30-day lookback)
        actual_low = expected + expected * Decimal("5") / Decimal("10000")
        for i in range(10):
            fill = ExecutionFill(
                opportunity_id=f"opp-stale-{i}",
                agent_name=agent,
                broker_id="ibkr",
                symbol="AAPL",
                side="BUY",
                expected_price=expected,
                actual_price=actual_low,
                quantity=Decimal("10"),
                filled_at=datetime.now(timezone.utc) - timedelta(days=40),  # stale
            )
            tracker._fills.setdefault(agent, []).append(fill)

        # get_recent_fills with max_days=30 should only return the 15 fresh ones
        recent = tracker.get_recent_fills(agent, limit=30, max_days=30)
        assert len(recent) == 15
        # All returned fills should be within the last 30 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        for f in recent:
            assert f.filled_at >= cutoff
