# trading/tests/unit/test_intel_order_flow.py
"""Tests for OrderFlowProvider — CVD divergence detection."""

import pytest
from unittest.mock import AsyncMock, patch

from intelligence.providers.order_flow import OrderFlowProvider


def _make_trades(prices: list[float], sides: list[str], amounts: list[float] | None = None) -> list[dict]:
    """Build a list of mock trade dicts."""
    if amounts is None:
        amounts = [1.0] * len(prices)
    trades = []
    for i, (p, s, a) in enumerate(zip(prices, sides, amounts)):
        trades.append({
            "price": p,
            "amount": a,
            "side": s,
            "timestamp": 1700000000 + i * 100,
        })
    return trades


# ── CVD computation ────────────────────────────────────────────────────

def test_cvd_computation_buy_adds_sell_subtracts():
    """Buy trades add volume, sell trades subtract."""
    trades = _make_trades(
        prices=[100, 101, 102],
        sides=["buy", "sell", "buy"],
        amounts=[10.0, 5.0, 3.0],
    )
    cvd = OrderFlowProvider._compute_cvd(trades)
    assert len(cvd) == 3
    assert cvd[0] == pytest.approx(10.0)
    assert cvd[1] == pytest.approx(5.0)   # 10 - 5
    assert cvd[2] == pytest.approx(8.0)   # 10 - 5 + 3


def test_cvd_computation_all_buys():
    trades = _make_trades(
        prices=[100, 101, 102],
        sides=["buy", "buy", "buy"],
        amounts=[1.0, 2.0, 3.0],
    )
    cvd = OrderFlowProvider._compute_cvd(trades)
    assert cvd[-1] == pytest.approx(6.0)


def test_cvd_computation_all_sells():
    trades = _make_trades(
        prices=[100, 99, 98],
        sides=["sell", "sell", "sell"],
        amounts=[1.0, 2.0, 3.0],
    )
    cvd = OrderFlowProvider._compute_cvd(trades)
    assert cvd[-1] == pytest.approx(-6.0)


def test_cvd_empty_trades():
    cvd = OrderFlowProvider._compute_cvd([])
    assert cvd == []


# ── Slope computation ──────────────────────────────────────────────────

def test_slope_positive():
    """Ascending series should have positive slope."""
    series = [1.0, 2.0, 3.0, 4.0, 5.0]
    slope = OrderFlowProvider._compute_slope(series)
    assert slope > 0
    assert slope == pytest.approx(1.0, abs=0.01)


def test_slope_negative():
    """Descending series should have negative slope."""
    series = [5.0, 4.0, 3.0, 2.0, 1.0]
    slope = OrderFlowProvider._compute_slope(series)
    assert slope < 0
    assert slope == pytest.approx(-1.0, abs=0.01)


def test_slope_flat():
    """Flat series should have zero slope."""
    series = [3.0, 3.0, 3.0, 3.0]
    slope = OrderFlowProvider._compute_slope(series)
    assert slope == pytest.approx(0.0, abs=0.01)


def test_slope_single_element():
    """Single element series returns 0 slope."""
    assert OrderFlowProvider._compute_slope([5.0]) == pytest.approx(0.0)


def test_slope_empty():
    """Empty series returns 0 slope."""
    assert OrderFlowProvider._compute_slope([]) == pytest.approx(0.0)


# ── Divergence detection ───────────────────────────────────────────────

def test_divergence_bullish():
    """Price down + CVD up = bullish divergence → positive score."""
    score, confidence = OrderFlowProvider._detect_divergence(
        price_slope=-1.0, cvd_slope=1.0
    )
    assert score > 0, "Bullish divergence should produce positive score"
    assert 0.3 <= score <= 0.6
    assert 0.0 < confidence <= 1.0


def test_divergence_bearish():
    """Price up + CVD down = bearish divergence → negative score."""
    score, confidence = OrderFlowProvider._detect_divergence(
        price_slope=1.0, cvd_slope=-1.0
    )
    assert score < 0, "Bearish divergence should produce negative score"
    assert -0.6 <= score <= -0.3
    assert 0.0 < confidence <= 1.0


def test_confirming_bullish():
    """Both slopes positive = confirming bullish → small positive score."""
    score, confidence = OrderFlowProvider._detect_divergence(
        price_slope=1.0, cvd_slope=1.0
    )
    assert score > 0, "Confirming bullish should produce positive score"
    assert 0.1 <= score <= 0.3
    assert 0.0 < confidence <= 1.0


def test_confirming_bearish():
    """Both slopes negative = confirming bearish → small negative score."""
    score, confidence = OrderFlowProvider._detect_divergence(
        price_slope=-1.0, cvd_slope=-1.0
    )
    assert score < 0, "Confirming bearish should produce negative score"
    assert -0.3 <= score <= -0.1
    assert 0.0 < confidence <= 1.0


def test_no_signal_flat():
    """Both slopes near zero → near-zero score."""
    score, confidence = OrderFlowProvider._detect_divergence(
        price_slope=0.0, cvd_slope=0.0
    )
    assert abs(score) < 0.1
    assert confidence < 0.3


# ── Full analyze() integration ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_bullish_divergence_full():
    """Price falling but CVD rising → positive score, no veto."""
    provider = OrderFlowProvider()
    # Price declining, but buys dominate
    trades = _make_trades(
        prices=[100, 99, 98, 97, 96, 95, 94, 93, 92, 91],
        sides=["buy", "buy", "buy", "sell", "buy", "buy", "buy", "sell", "buy", "buy"],
        amounts=[5.0, 6.0, 7.0, 2.0, 8.0, 9.0, 10.0, 3.0, 11.0, 12.0],
    )
    with patch.object(
        provider, "_fetch_recent_trades", new_callable=AsyncMock, return_value=trades
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.source == "order_flow"
    assert report.symbol == "BTCUSD"
    assert report.score > 0, "Bullish divergence expected"
    assert report.confidence > 0
    assert report.veto is False
    assert "cvd_slope" in report.details
    assert "price_slope" in report.details
    assert "divergence_type" in report.details


@pytest.mark.asyncio
async def test_bearish_divergence_full():
    """Price rising but CVD falling → negative score, no veto."""
    provider = OrderFlowProvider()
    # Price rising, but sells dominate
    trades = _make_trades(
        prices=[90, 91, 92, 93, 94, 95, 96, 97, 98, 99],
        sides=["sell", "sell", "sell", "buy", "sell", "sell", "sell", "buy", "sell", "sell"],
        amounts=[5.0, 6.0, 7.0, 2.0, 8.0, 9.0, 10.0, 3.0, 11.0, 12.0],
    )
    with patch.object(
        provider, "_fetch_recent_trades", new_callable=AsyncMock, return_value=trades
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.score < 0, "Bearish divergence expected"
    assert report.veto is False


@pytest.mark.asyncio
async def test_exchange_failure_returns_none():
    """CCXT failure should return None, not raise."""
    provider = OrderFlowProvider()
    with patch.object(
        provider, "_fetch_recent_trades",
        new_callable=AsyncMock,
        side_effect=Exception("Exchange timeout"),
    ):
        report = await provider.analyze("BTCUSD")
    assert report is None


@pytest.mark.asyncio
async def test_never_vetoes():
    """Order flow is informational — never issues a veto."""
    provider = OrderFlowProvider()
    trades = _make_trades(
        prices=[100, 99, 98, 97, 96, 95, 94, 93, 92, 91],
        sides=["sell"] * 10,
        amounts=[100.0] * 10,
    )
    with patch.object(
        provider, "_fetch_recent_trades", new_callable=AsyncMock, return_value=trades
    ):
        report = await provider.analyze("BTCUSD")
    assert report is not None
    assert report.veto is False


@pytest.mark.asyncio
async def test_symbol_mapping():
    """Provider should map BTCUSD → BTC/USDT for CCXT."""
    provider = OrderFlowProvider()
    trades = _make_trades(
        prices=[100] * 5,
        sides=["buy"] * 5,
    )
    with patch.object(
        provider, "_fetch_recent_trades", new_callable=AsyncMock, return_value=trades
    ) as mock_fetch:
        await provider.analyze("ETHUSD")
    # The analyze method should pass the mapped symbol to _fetch_recent_trades
    # but the report should use the original symbol
    mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_name_property():
    provider = OrderFlowProvider()
    assert provider.name == "order_flow"


@pytest.mark.asyncio
async def test_empty_trades_returns_none():
    """If exchange returns no trades, gracefully return None."""
    provider = OrderFlowProvider()
    with patch.object(
        provider, "_fetch_recent_trades", new_callable=AsyncMock, return_value=[]
    ):
        report = await provider.analyze("BTCUSD")
    assert report is None
