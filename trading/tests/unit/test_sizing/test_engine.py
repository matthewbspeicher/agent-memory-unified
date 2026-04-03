"""Tests for SizingEngine with trust-scaled Kelly sizing."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sizing.engine import SizingEngine
from agents.models import TrustLevel
from storage.performance import PerformanceSnapshot


def _snapshot(win_rate=0.6, avg_win="100", avg_loss="80", total_trades=60):
    return PerformanceSnapshot(
        agent_name="test", timestamp="2026-01-01",
        opportunities_generated=100, opportunities_executed=60,
        win_rate=win_rate, avg_win=Decimal(avg_win), avg_loss=Decimal(avg_loss),
        total_trades=total_trades,
    )


class TestSizingEngine:
    @pytest.mark.asyncio
    async def test_monitored_gets_quarter_kelly(self):
        store = MagicMock()
        store.get_latest = AsyncMock(return_value=_snapshot())
        engine = SizingEngine(perf_store=store)
        size = await engine.compute_size("test", TrustLevel.MONITORED, Decimal("150"), Decimal("50000"))
        assert size > Decimal("0")

    @pytest.mark.asyncio
    async def test_autonomous_gets_more(self):
        store = MagicMock()
        store.get_latest = AsyncMock(return_value=_snapshot())
        engine = SizingEngine(perf_store=store)
        m = await engine.compute_size("test", TrustLevel.MONITORED, Decimal("150"), Decimal("50000"))
        a = await engine.compute_size("test", TrustLevel.AUTONOMOUS, Decimal("150"), Decimal("50000"))
        assert a > m

    @pytest.mark.asyncio
    async def test_no_data_returns_minimum(self):
        store = MagicMock()
        store.get_latest = AsyncMock(return_value=None)
        engine = SizingEngine(perf_store=store)
        size = await engine.compute_size("test", TrustLevel.MONITORED, Decimal("100"), Decimal("10000"))
        assert size == Decimal("1")

    @pytest.mark.asyncio
    async def test_few_trades_returns_minimum(self):
        store = MagicMock()
        store.get_latest = AsyncMock(return_value=_snapshot(total_trades=5))
        engine = SizingEngine(perf_store=store, min_trades=30)
        size = await engine.compute_size("test", TrustLevel.AUTONOMOUS, Decimal("100"), Decimal("10000"))
        assert size == Decimal("1")
