import pytest
from unittest.mock import AsyncMock, patch

from intelligence.providers.anomaly import AnomalyProvider


@pytest.mark.asyncio
async def test_anomaly_high_volume_aligned():
    provider = AnomalyProvider()
    with patch.object(
        provider, "_fetch_volume_ratio", new_callable=AsyncMock, return_value=3.5
    ):
        with patch.object(
            provider, "_fetch_price_direction", new_callable=AsyncMock, return_value=1.0
        ):
            with patch.object(
                provider,
                "_fetch_spread_ratio",
                new_callable=AsyncMock,
                return_value=1.0,
            ):
                report = await provider.analyze("BTCUSD")
    assert report is not None
    assert report.source == "anomaly"
    assert report.score > 0
    assert report.veto is False


@pytest.mark.asyncio
async def test_anomaly_high_volume_diverges():
    provider = AnomalyProvider()
    with patch.object(
        provider, "_fetch_volume_ratio", new_callable=AsyncMock, return_value=3.5
    ):
        with patch.object(
            provider,
            "_fetch_price_direction",
            new_callable=AsyncMock,
            return_value=-1.0,
        ):
            with patch.object(
                provider,
                "_fetch_spread_ratio",
                new_callable=AsyncMock,
                return_value=1.0,
            ):
                report = await provider.analyze("BTCUSD")
    assert report is not None
    assert report.score < 0


@pytest.mark.asyncio
async def test_anomaly_veto_extreme_volume():
    provider = AnomalyProvider()
    with patch.object(
        provider, "_fetch_volume_ratio", new_callable=AsyncMock, return_value=6.0
    ):
        with patch.object(
            provider,
            "_fetch_price_direction",
            new_callable=AsyncMock,
            return_value=-1.0,
        ):
            with patch.object(
                provider,
                "_fetch_spread_ratio",
                new_callable=AsyncMock,
                return_value=1.5,
            ):
                report = await provider.analyze("BTCUSD")
    assert report is not None
    assert report.veto is True


@pytest.mark.asyncio
async def test_anomaly_normal_conditions():
    provider = AnomalyProvider()
    with patch.object(
        provider, "_fetch_volume_ratio", new_callable=AsyncMock, return_value=1.2
    ):
        with patch.object(
            provider, "_fetch_price_direction", new_callable=AsyncMock, return_value=0.5
        ):
            with patch.object(
                provider,
                "_fetch_spread_ratio",
                new_callable=AsyncMock,
                return_value=1.0,
            ):
                report = await provider.analyze("BTCUSD")
    assert report is not None
    assert abs(report.score) < 0.15
    assert report.veto is False


@pytest.mark.asyncio
async def test_anomaly_api_failure_returns_none():
    provider = AnomalyProvider()
    with patch.object(
        provider,
        "_fetch_volume_ratio",
        new_callable=AsyncMock,
        side_effect=Exception("exchange down"),
    ):
        report = await provider.analyze("BTCUSD")
    assert report is None
