import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from broker.models import PredictionContract, AssetType
from agents.models import AgentConfig, ActionLevel
from strategies.polymarket_news_arb import PolymarketNewsArbAgent
from strategies.cross_platform_arb import CrossPlatformArbAgent
from adapters.polymarket.data_source import PolymarketDataSource
from adapters.kalshi.data_source import KalshiDataSource

@pytest.fixture
def mock_poly_ds():
    ds = MagicMock(spec=PolymarketDataSource)
    ds.get_markets = AsyncMock(return_value=[
        PredictionContract(
            ticker="0xABC", title="Test News Market", category="politics",
            close_time="2026-12-31T00:00:00Z", yes_bid=40, volume_24h=1000
        )
    ])
    return ds

@pytest.fixture
def mock_kalshi_ds():
    ds = MagicMock()
    ds.get_markets = AsyncMock(return_value=[
        PredictionContract(
            ticker="KALSHI-123", title="Test News Market", category="politics",
            close_time=datetime(2026, 12, 31, tzinfo=timezone.utc), yes_bid=55, volume_24h=1000
        )
    ])
    return ds

@pytest.fixture
def mock_app_state(mock_poly_ds, mock_kalshi_ds):
    class MockDataBus:
        providers = [mock_poly_ds, mock_kalshi_ds]
    state = MagicMock()
    state.brokers = {"polymarket": MagicMock(), "kalshi": MagicMock()}
    state.data_bus = MockDataBus()
    state.data_bus._polymarket_source = mock_poly_ds
    return state

@pytest.mark.asyncio
async def test_polymarket_news_arb_agent(mock_app_state):
    config = AgentConfig(name="poly_arb", strategy="polymarket_news_arb", schedule="on_demand", action_level=ActionLevel.SUGGEST_TRADE)
    config._app_state = mock_app_state
    
    agent = PolymarketNewsArbAgent(config=config)
    agent._fetch_recent_headlines = AsyncMock(return_value=["Headline 1", "Headline 2"])
    
    # Mock LLM to return a 70% prob, creating a 30c gap (40c market vs 70c LLM)
    agent.structured_call = AsyncMock(return_value={"implied_probability": 70, "confidence": 90, "reasoning": "sure"})
    
    opps = await agent.scan(mock_app_state.data_bus)
    assert len(opps) == 2
    assert opps[0].broker_id == "polymarket"
    assert opps[0].symbol.ticker == "0xABC"
    assert opps[0].suggested_trade.side.value == "BUY"
    assert "70" in str(opps[0].data)

@pytest.mark.asyncio
async def test_cross_platform_arb_agent(mock_kalshi_ds, mock_poly_ds):
    config = AgentConfig(name="x_arb", strategy="cross_platform_arb", schedule="on_demand", action_level=ActionLevel.SUGGEST_TRADE)
    agent = CrossPlatformArbAgent(config=config, kalshi_ds=mock_kalshi_ds, polymarket_ds=mock_poly_ds)
    
    # 40c Poly vs 55c Kalshi -> 15c spread
    opps = await agent.scan(MagicMock())
    assert len(opps) == 1
    assert opps[0].broker_id == "polymarket" # Poly is cheaper (40c)
    assert opps[0].symbol.ticker == "0xABC"
    assert opps[0].suggested_trade.limit_price == Decimal("0.4")
    assert opps[0].data["gap_cents"] == 15
    assert opps[0].data["kalshi_cents"] == 55

@pytest.mark.asyncio
async def test_cross_platform_arb_zero_spread(mock_kalshi_ds, mock_poly_ds):
    # Tie breaking case
    import dataclasses
    orig = mock_poly_ds.get_markets.return_value[0]
    mock_poly_ds.get_markets.return_value[0] = dataclasses.replace(orig, yes_bid=55)
    
    config = AgentConfig(name="x_arb", strategy="cross_platform_arb", schedule="on_demand", action_level=ActionLevel.SUGGEST_TRADE)
    agent = CrossPlatformArbAgent(config=config, kalshi_ds=mock_kalshi_ds, polymarket_ds=mock_poly_ds)
    
    opps = await agent.scan(MagicMock())
    assert len(opps) == 0 # 0 spread, no trade
