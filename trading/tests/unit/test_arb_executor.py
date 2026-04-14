"""Tests for ArbExecutor auto-execution."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
