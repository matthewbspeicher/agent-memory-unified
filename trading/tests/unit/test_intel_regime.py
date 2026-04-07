import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from intelligence.providers.regime import RegimeProvider


def _make_bars(prices: list[float]):
    """Create mock Bar objects from a price list."""
    from broker.models import Bar, Symbol, AssetType

    bars = []
    for i, p in enumerate(prices):
        bars.append(
            Bar(
                symbol=Symbol(ticker="BTCUSD", asset_type=AssetType.FOREX),
                timestamp=datetime(2026, 4, 7, i, 0, tzinfo=timezone.utc),
                close=Decimal(str(p)),
            )
        )
    return bars


@pytest.mark.asyncio
async def test_regime_without_memory_returns_none():
    provider = RegimeProvider(memory_manager=None)
    report = await provider.analyze("BTCUSD")
    assert report is None


@pytest.mark.asyncio
async def test_regime_trending_bull_with_memories():
    mm = MagicMock()
    mm.detect_regime.return_value = "trending_bull"
    mm.recall_similar_regimes = AsyncMock(
        return_value=[
            {"id": "1", "value": "past regime"},
            {"id": "2", "value": "another past regime"},
            {"id": "3", "value": "yet another"},
        ]
    )
    mm.store_regime = AsyncMock()

    provider = RegimeProvider(memory_manager=mm)

    # Trending bull: steadily rising prices
    bars = _make_bars([100, 101, 102, 103, 104, 105])
    with patch.object(
        provider, "_fetch_bars", new_callable=AsyncMock, return_value=bars
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.source == "regime"
    assert report.score == 0.0  # regime doesn't dictate direction
    assert report.confidence == 0.8  # 0.5 + 3*0.1
    assert report.veto is False
    assert report.details["regime"] == "trending_bull"
    assert report.details["recalled_count"] == 3


@pytest.mark.asyncio
async def test_regime_no_memories_low_confidence():
    mm = MagicMock()
    mm.detect_regime.return_value = "volatile_range"
    mm.recall_similar_regimes = AsyncMock(return_value=[])
    mm.store_regime = AsyncMock()

    provider = RegimeProvider(memory_manager=mm)
    bars = _make_bars([100, 102, 98, 101, 97, 103])

    with patch.object(
        provider, "_fetch_bars", new_callable=AsyncMock, return_value=bars
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.confidence == 0.5  # no memories = base confidence only


@pytest.mark.asyncio
async def test_regime_fetch_bars_failure():
    mm = MagicMock()
    provider = RegimeProvider(memory_manager=mm)

    with patch.object(
        provider,
        "_fetch_bars",
        new_callable=AsyncMock,
        side_effect=Exception("no data"),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is None


@pytest.mark.asyncio
async def test_regime_never_vetoes():
    mm = MagicMock()
    mm.detect_regime.return_value = "trending_bear"
    mm.recall_similar_regimes = AsyncMock(return_value=[{"id": "1"}] * 10)
    mm.store_regime = AsyncMock()

    provider = RegimeProvider(memory_manager=mm)
    bars = _make_bars([100, 99, 98, 97, 96, 95])

    with patch.object(
        provider, "_fetch_bars", new_callable=AsyncMock, return_value=bars
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.veto is False
    assert report.confidence == 1.0  # capped at 1.0 (0.5 + 10*0.1)
