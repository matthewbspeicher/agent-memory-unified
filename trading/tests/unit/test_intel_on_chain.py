# trading/tests/unit/test_intel_on_chain.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from intelligence.providers.on_chain import OnChainProvider


@pytest.mark.asyncio
async def test_on_chain_accumulation_bullish():
    provider = OnChainProvider()
    with patch.object(provider, "_fetch_exchange_netflow", new_callable=AsyncMock, return_value=-5000.0):
        with patch.object(provider, "_fetch_exchange_netflow_30d_avg", new_callable=AsyncMock, return_value=2000.0):
            report = await provider.analyze("BTCUSD")
    assert report is not None
    assert report.source == "on_chain"
    assert report.score > 0
    assert report.veto is False


@pytest.mark.asyncio
async def test_on_chain_distribution_bearish():
    provider = OnChainProvider()
    with patch.object(provider, "_fetch_exchange_netflow", new_callable=AsyncMock, return_value=3000.0):
        with patch.object(provider, "_fetch_exchange_netflow_30d_avg", new_callable=AsyncMock, return_value=2000.0):
            report = await provider.analyze("BTCUSD")
    assert report is not None
    assert report.score < 0
    assert report.veto is False


@pytest.mark.asyncio
async def test_on_chain_veto_on_massive_inflow():
    provider = OnChainProvider()
    with patch.object(provider, "_fetch_exchange_netflow", new_callable=AsyncMock, return_value=5000.0):
        with patch.object(provider, "_fetch_exchange_netflow_30d_avg", new_callable=AsyncMock, return_value=2000.0):
            report = await provider.analyze("BTCUSD")
    assert report is not None
    assert report.veto is True
    assert report.veto_reason is not None


@pytest.mark.asyncio
async def test_on_chain_api_failure_returns_none():
    provider = OnChainProvider(coinglass_api_key=None)
    with patch.object(provider, "_fetch_exchange_netflow", new_callable=AsyncMock, side_effect=Exception("No API key")):
        report = await provider.analyze("BTCUSD")
    assert report is None
