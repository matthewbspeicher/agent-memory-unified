# trading/tests/unit/test_intel_providers.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from intelligence.providers.sentiment import SentimentProvider


@pytest.mark.asyncio
async def test_sentiment_extreme_fear():
    provider = SentimentProvider()
    with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, return_value=15):
        report = await provider.analyze("BTCUSD")
    assert report is not None
    assert report.source == "sentiment"
    assert report.score > 0
    assert report.veto is False


@pytest.mark.asyncio
async def test_sentiment_extreme_greed():
    provider = SentimentProvider()
    with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, return_value=85):
        report = await provider.analyze("BTCUSD")
    assert report is not None
    assert report.score < 0
    assert report.veto is False


@pytest.mark.asyncio
async def test_sentiment_neutral():
    provider = SentimentProvider()
    with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, return_value=50):
        report = await provider.analyze("BTCUSD")
    assert report is not None
    assert abs(report.score) < 0.1


@pytest.mark.asyncio
async def test_sentiment_api_failure_returns_none():
    provider = SentimentProvider()
    with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, side_effect=Exception("API down")):
        report = await provider.analyze("BTCUSD")
    assert report is None


@pytest.mark.asyncio
async def test_sentiment_never_vetoes():
    provider = SentimentProvider()
    for value in [0, 10, 50, 90, 100]:
        with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, return_value=value):
            report = await provider.analyze("BTCUSD")
        if report is not None:
            assert report.veto is False
