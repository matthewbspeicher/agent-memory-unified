"""Tests for DataBus summary methods (get_market_summary, get_key_levels, etc.)."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from broker.models import Bar, Quote, Symbol
from data.bus import DataBus


def _make_bars(n: int = 50, base_price: float = 100.0) -> list[Bar]:
    bars = []
    sym = Symbol(ticker="TEST")
    for i in range(n):
        price = base_price + i * 0.5
        bars.append(
            Bar(
                symbol=sym,
                timestamp=datetime(2026, 1, 1 + i % 28, 12, 0),
                open=Decimal(str(price - 0.2)),
                high=Decimal(str(price + 1.0)),
                low=Decimal(str(price - 1.0)),
                close=Decimal(str(price)),
                volume=1000000 + i * 10000,
            )
        )
    return bars


def _make_quote(last: float = 125.0) -> Quote:
    return Quote(
        symbol=Symbol(ticker="TEST"),
        last=Decimal(str(last)),
        bid=Decimal(str(last - 0.1)),
        ask=Decimal(str(last + 0.1)),
        volume=5000000,
    )


@pytest.fixture
def data_bus():
    """DataBus with mocked sources."""
    source = MagicMock()
    source.supports_quotes = True
    source.supports_historical = True
    source.get_quote = AsyncMock(return_value=_make_quote())
    source.get_historical = AsyncMock(return_value=_make_bars(50))
    return DataBus(sources=[source])


class TestGetMarketSummary:
    @pytest.mark.asyncio
    async def test_returns_compact_dict(self, data_bus: DataBus):
        sym = Symbol(ticker="TEST")
        summary = await data_bus.get_market_summary(sym)

        assert summary["symbol"] == "TEST"
        assert summary["price"] is not None
        assert "rsi_14" in summary
        assert "ema_20" in summary
        assert "macd_histogram" in summary
        assert "bb_width" in summary
        assert "atr_14" in summary

    @pytest.mark.asyncio
    async def test_handles_partial_failures(self):
        source = MagicMock()
        source.supports_quotes = True
        source.supports_historical = True
        source.get_quote = AsyncMock(return_value=_make_quote())
        source.get_historical = AsyncMock(side_effect=RuntimeError("no data"))
        bus = DataBus(sources=[source])

        summary = await bus.get_market_summary(Symbol(ticker="FAIL"))
        assert summary["price"] == 125.0
        # Indicators that depend on historical should be missing, not error
        assert "rsi_14" not in summary


class TestGetKeyLevels:
    @pytest.mark.asyncio
    async def test_returns_pivot_and_sr(self, data_bus: DataBus):
        levels = await data_bus.get_key_levels(Symbol(ticker="TEST"))

        assert "pivot" in levels
        assert "r1" in levels
        assert "s1" in levels
        assert "recent_high" in levels
        assert "recent_low" in levels
        assert levels["recent_high"] > levels["recent_low"]


class TestGetVolatilitySummary:
    @pytest.mark.asyncio
    async def test_returns_vol_metrics(self, data_bus: DataBus):
        vol = await data_bus.get_volatility_summary(Symbol(ticker="TEST"))

        assert "atr_14" in vol
        assert "atr_pct" in vol
        assert "bb_width" in vol
        assert "avg_daily_range" in vol
        assert vol["atr_14"] > 0


class TestGetHistoricalSummary:
    @pytest.mark.asyncio
    async def test_returns_stats_not_bars(self, data_bus: DataBus):
        summary = await data_bus.get_historical_summary(Symbol(ticker="TEST"))

        assert summary["bar_count"] == 50
        assert "open_first" in summary
        assert "close_last" in summary
        assert "high" in summary
        assert "low" in summary
        assert "avg_volume" in summary
        assert summary["trend"] in ("up", "down", "flat")
        assert "change_pct" in summary
