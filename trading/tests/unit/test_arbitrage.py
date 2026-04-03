import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
from execution.arbitrage import ArbCoordinator
from execution.models import ArbTrade, ArbLeg, ArbState, SequencingStrategy
from broker.models import OrderBase, Symbol, AssetType, OrderResult, OrderStatus

@pytest.fixture
def mock_brokers():
    kalshi_mock = MagicMock()
    kalshi_mock.market_data.ds.get_live_quote = AsyncMock(return_value=Decimal("0.5"))
    kalshi_mock.orders = MagicMock()
    kalshi_mock.orders.place_order = AsyncMock()
    
    poly_mock = MagicMock()
    poly_mock.market_data.ds.get_live_quote = AsyncMock(return_value=Decimal("0.5"))
    poly_mock.orders = MagicMock()
    poly_mock.orders.place_order = AsyncMock()
    
    return {"kalshi": kalshi_mock, "polymarket": poly_mock}

@pytest.fixture
def mock_store():
    store = MagicMock()
    store.save_trade = AsyncMock()
    store.update_trade_state = AsyncMock()
    store.update_leg = AsyncMock()
    store.update_leg_atomic = AsyncMock()
    return store

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.order_timeout = 30
    settings.arb_toxicity_threshold = 0.7
    return settings

@pytest.fixture
def sample_trade():
    symbol_a = Symbol(ticker="K-1", asset_type=AssetType.PREDICTION)
    symbol_b = Symbol(ticker="P-1", asset_type=AssetType.PREDICTION)
    
    leg_a = ArbLeg(broker_id="kalshi", order=OrderBase(symbol=symbol_a, side="BUY", quantity=Decimal("10"), account_id="U123"))
    leg_b = ArbLeg(broker_id="polymarket", order=OrderBase(symbol=symbol_b, side="SELL", quantity=Decimal("10"), account_id="U123"))
    
    return ArbTrade(
        id="arb-123",
        symbol_a="K-1",
        symbol_b="P-1",
        leg_a=leg_a,
        leg_b=leg_b,
        expected_profit_bps=50
    )

@pytest.mark.asyncio
async def test_arb_success(mock_brokers, mock_store, mock_settings, sample_trade):
    coordinator = ArbCoordinator(mock_brokers, mock_store, mock_settings)
    
    # Mock successful fills
    res_a = OrderResult(order_id="ext-a", status=OrderStatus.FILLED, avg_fill_price=Decimal("0.5"), filled_quantity=Decimal("10"), )
    res_b = OrderResult(order_id="ext-b", status=OrderStatus.FILLED, avg_fill_price=Decimal("0.6"), filled_quantity=Decimal("10"), )

    async def mock_place_order_a(*args, **kwargs):
        return res_a
    async def mock_place_order_b(*args, **kwargs):
        return res_b
    
    mock_brokers["kalshi"].orders.place_order = mock_place_order_a
    mock_brokers["polymarket"].orders.place_order = mock_place_order_b
    
    success = await coordinator.execute_arbitrage(sample_trade)
    
    assert success
    assert mock_store.update_trade_state.called
    # Last state should be COMPLETED
    args, _ = mock_store.update_trade_state.call_args_list[-1]
    assert args[1] == ArbState.COMPLETED

@pytest.mark.asyncio
async def test_arb_leg_b_failure_unwind(mock_brokers, mock_store, mock_settings, sample_trade):
    coordinator = ArbCoordinator(mock_brokers, mock_store, mock_settings)
    
    # Leg A fills, Leg B fails
    res_a = OrderResult(order_id="ext-a", status=OrderStatus.FILLED, avg_fill_price=Decimal("0.5"), filled_quantity=Decimal("10"), )
    
    async def mock_place_order_a(*args, **kwargs):
        return res_a
    async def mock_place_order_b(*args, **kwargs):
        raise Exception("API Error")

    mock_brokers["kalshi"].orders.place_order = mock_place_order_a
    mock_brokers["polymarket"].orders.place_order = mock_place_order_b
    
    success = await coordinator.execute_arbitrage(sample_trade)
    
    assert not success
    # Should have attempted unwind
    unwind_call_exists = any("unwinding" in str(c) for c in mock_store.update_trade_state.call_args_list)
    assert unwind_call_exists
