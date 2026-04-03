"""Tests for BacktestSandbox — Hermes parameter evaluation engine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backtesting.sandbox import BacktestSandbox, SandboxResult
from broker.models import Bar, Symbol, AssetType


# --- Fixtures ---

def _make_bars(ticker: str, num_bars: int = 120, base_price: float = 100.0) -> list[Bar]:
    """Generate synthetic daily bars with mild uptrend and noise."""
    import random
    random.seed(42)

    symbol = Symbol(ticker=ticker, asset_type=AssetType.STOCK)
    bars = []
    price = base_price
    start = datetime(2025, 1, 2, tzinfo=timezone.utc)

    for i in range(num_bars):
        # Random walk with slight upward drift
        change = random.gauss(0.001, 0.02)
        price *= (1 + change)
        high = price * (1 + abs(random.gauss(0, 0.01)))
        low = price * (1 - abs(random.gauss(0, 0.01)))
        volume = random.randint(500_000, 5_000_000)

        bars.append(Bar(
            symbol=symbol,
            open=Decimal(str(round(price * 0.999, 2))),
            high=Decimal(str(round(high, 2))),
            low=Decimal(str(round(low, 2))),
            close=Decimal(str(round(price, 2))),
            volume=volume,
            timestamp=start + timedelta(days=i),
        ))

    return bars


class MockDataBus:
    """Minimal DataBus mock that returns pre-loaded historical data."""

    def __init__(self, bars_by_ticker: dict[str, list[Bar]]) -> None:
        self._bars = bars_by_ticker

    async def get_historical(
        self, symbol: Symbol, timeframe: str = "1d", period: str = "3mo",
    ) -> list[Bar]:
        bars = self._bars.get(symbol.ticker, [])
        if not bars:
            raise ValueError(f"No data for {symbol.ticker}")
        return bars


# --- Tests ---

class TestSandboxResult:
    def test_to_dict(self):
        result = SandboxResult(
            strategy="rsi",
            parameters={"period": 14},
            symbols_tested=["AAPL"],
            period="6mo",
            sharpe_ratio=1.5,
            total_trades=50,
            is_viable=True,
        )
        d = result.to_dict()
        assert d["strategy"] == "rsi"
        assert d["sharpe_ratio"] == 1.5
        assert d["is_viable"] is True
        assert isinstance(d["parameters"], dict)

    def test_error_result(self):
        result = SandboxResult(
            strategy="rsi",
            parameters={},
            symbols_tested=[],
            period="6mo",
            error="No data",
        )
        assert result.is_viable is False
        assert result.error == "No data"


class TestBacktestSandbox:
    @pytest.fixture
    def mock_bus(self) -> MockDataBus:
        return MockDataBus({
            "AAPL": _make_bars("AAPL", 120, 150.0),
            "MSFT": _make_bars("MSFT", 120, 300.0),
        })

    @pytest.fixture
    def sandbox(self, mock_bus: MockDataBus) -> BacktestSandbox:
        return BacktestSandbox(
            data_bus=mock_bus,
            min_sharpe=0.0,
            min_trades=1,
            max_drawdown=50.0,
        )

    @pytest.mark.asyncio
    async def test_evaluate_rsi_strategy(self, sandbox: BacktestSandbox):
        result = await sandbox.evaluate(
            strategy="rsi",
            parameters={"period": 14, "oversold": 30, "overbought": 70},
            symbols=["AAPL", "MSFT"],
            period="6mo",
        )

        assert result.error is None
        assert result.strategy == "rsi"
        assert result.evaluation_time_ms > 0
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.total_trades, int)
        assert "AAPL" in result.symbols_tested or "MSFT" in result.symbols_tested

    @pytest.mark.asyncio
    async def test_evaluate_unknown_strategy(self, sandbox: BacktestSandbox):
        result = await sandbox.evaluate(
            strategy="nonexistent_strategy_xyz",
            parameters={},
            symbols=["AAPL"],
        )

        assert result.error is not None
        assert "Unknown strategy" in result.error
        assert result.is_viable is False

    @pytest.mark.asyncio
    async def test_evaluate_no_data(self):
        empty_bus = MockDataBus({})
        sandbox = BacktestSandbox(data_bus=empty_bus)

        result = await sandbox.evaluate(
            strategy="rsi",
            parameters={"period": 14},
            symbols=["FAKE"],
        )

        assert result.error is not None
        assert result.is_viable is False

    @pytest.mark.asyncio
    async def test_evaluate_timeout(self, mock_bus: MockDataBus):
        sandbox = BacktestSandbox(data_bus=mock_bus, timeout_seconds=0)

        result = await sandbox.evaluate(
            strategy="rsi",
            parameters={"period": 14},
            symbols=["AAPL"],
        )

        # With 0 timeout, should timeout immediately
        assert result.error is not None
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_evaluate_variants(self, sandbox: BacktestSandbox):
        base_params = {"period": 14, "oversold": 30, "overbought": 70}
        variants = [
            {"period": 10, "oversold": 25},
            {"period": 20, "oversold": 35},
        ]

        results = await sandbox.evaluate_variants(
            strategy="rsi",
            base_parameters=base_params,
            variants=variants,
            symbols=["AAPL"],
            period="6mo",
        )

        assert len(results) == 2
        # Should be sorted by (is_viable, sharpe_ratio) descending
        for r in results:
            assert r.error is None
            assert r.strategy == "rsi"

    @pytest.mark.asyncio
    async def test_viability_check(self, mock_bus: MockDataBus):
        strict_sandbox = BacktestSandbox(
            data_bus=mock_bus,
            min_sharpe=99.0,  # impossibly high
            min_trades=1,
            max_drawdown=50.0,
        )

        result = await strict_sandbox.evaluate(
            strategy="rsi",
            parameters={"period": 14, "oversold": 30, "overbought": 70},
            symbols=["AAPL"],
        )

        # With Sharpe threshold of 99, nothing should be viable
        assert result.is_viable is False

    @pytest.mark.asyncio
    async def test_symbol_truncation(self, mock_bus: MockDataBus):
        """Verify sandox handles large symbol lists gracefully."""
        # Generate 60 symbols (exceeds MAX_SYMBOLS=50),
        # but only AAPL and MSFT have data
        symbols = [f"SYM{i}" for i in range(60)]
        symbols[0] = "AAPL"
        symbols[1] = "MSFT"

        sandbox = BacktestSandbox(
            data_bus=mock_bus,
            min_sharpe=0.0,
            min_trades=0,
            max_drawdown=100.0,
        )

        result = await sandbox.evaluate(
            strategy="rsi",
            parameters={"period": 14, "oversold": 30, "overbought": 70},
            symbols=symbols,
        )

        # Should not error — truncates to first 50 and silently skips missing data
        assert result.error is None



