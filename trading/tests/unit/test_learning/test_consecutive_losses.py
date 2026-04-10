"""Tests for consecutive loss circuit breaker in StrategyHealthEngine."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from learning.strategy_health import (
    StrategyHealthConfig,
    StrategyHealthEngine,
    StrategyHealthStatus,
)


@pytest.fixture
def mock_health_store():
    store = MagicMock()
    store.get_status = AsyncMock(return_value=None)
    store.upsert_status = AsyncMock()
    store.record_event = AsyncMock()
    return store


@pytest.fixture
def mock_perf_store():
    store = MagicMock()
    return store


@pytest.fixture
def config_with_circuit_breaker():
    return StrategyHealthConfig(
        enabled=True,
        max_consecutive_losses=5,
        consecutive_loss_cooldown_hours=48,
        default_min_trade_count=10,
    )


class TestConsecutiveLossCircuitBreaker:
    @pytest.mark.asyncio
    async def test_triggers_on_max_consecutive_losses(
        self, mock_health_store, mock_perf_store, config_with_circuit_breaker
    ):
        mock_perf_store.get_latest = AsyncMock(
            return_value=MagicMock(
                total_trades=50,
                avg_win=Decimal("100"),
                avg_loss=Decimal("50"),
                win_rate=Decimal("0.5"),
                max_drawdown=Decimal("1000"),
                total_pnl=Decimal("500"),
                profit_factor=Decimal("1.5"),
                consecutive_losses=5,  # At threshold
            )
        )

        engine = StrategyHealthEngine(
            health_store=mock_health_store,
            perf_store=mock_perf_store,
            config=config_with_circuit_breaker,
        )

        status = await engine.evaluate("test_agent")
        assert status == StrategyHealthStatus.THROTTLED

        # Verify upsert was called with circuit breaker reason
        mock_health_store.upsert_status.assert_called_once()
        call_kwargs = mock_health_store.upsert_status.call_args[1]
        assert "Circuit breaker" in call_kwargs["trigger_reason"]

    @pytest.mark.asyncio
    async def test_no_trigger_below_threshold(
        self, mock_health_store, mock_perf_store, config_with_circuit_breaker
    ):
        """Boundary: N=4 with max=5 must NOT trip the circuit breaker.

        Tightened from `in (NORMAL, WATCHLIST)` to `!= THROTTLED` so a
        `>=` → `>` regression (which would stop firing at N=5) is
        caught by this test.
        """
        mock_perf_store.get_latest = AsyncMock(
            return_value=MagicMock(
                total_trades=50,
                avg_win=Decimal("100"),
                avg_loss=Decimal("50"),
                win_rate=Decimal("0.5"),
                max_drawdown=Decimal("1000"),
                total_pnl=Decimal("500"),
                profit_factor=Decimal("1.5"),
                consecutive_losses=4,  # Exactly one below threshold
            )
        )

        engine = StrategyHealthEngine(
            health_store=mock_health_store,
            perf_store=mock_perf_store,
            config=config_with_circuit_breaker,
        )

        status = await engine.evaluate("test_agent")
        assert status != StrategyHealthStatus.THROTTLED, (
            "Circuit breaker tripped at N=4 when max=5 — off-by-one regression"
        )

    @pytest.mark.asyncio
    async def test_circuit_breaker_overrides_other_checks(
        self, mock_health_store, mock_perf_store, config_with_circuit_breaker
    ):
        # Even with good expectancy, circuit breaker should trigger
        mock_perf_store.get_latest = AsyncMock(
            return_value=MagicMock(
                total_trades=50,
                avg_win=Decimal("200"),
                avg_loss=Decimal("10"),
                win_rate=Decimal("0.8"),
                max_drawdown=Decimal("500"),
                total_pnl=Decimal("5000"),
                profit_factor=Decimal("3.0"),
                consecutive_losses=6,  # Above threshold
            )
        )

        engine = StrategyHealthEngine(
            health_store=mock_health_store,
            perf_store=mock_perf_store,
            config=config_with_circuit_breaker,
        )

        status = await engine.evaluate("test_agent")
        assert status == StrategyHealthStatus.THROTTLED

    @pytest.mark.asyncio
    async def test_disabled_engine_returns_normal(
        self, mock_health_store, mock_perf_store
    ):
        config = StrategyHealthConfig(enabled=False, max_consecutive_losses=5)
        mock_perf_store.get_latest = AsyncMock(
            return_value=MagicMock(
                total_trades=50,
                consecutive_losses=10,  # Way above threshold
            )
        )

        engine = StrategyHealthEngine(
            health_store=mock_health_store,
            perf_store=mock_perf_store,
            config=config,
        )

        status = await engine.evaluate("test_agent")
        assert status == StrategyHealthStatus.NORMAL
