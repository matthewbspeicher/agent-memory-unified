import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from decimal import Decimal
from execution.arbitrage import ArbCoordinator
from execution.models import ArbTrade, ArbLeg, ArbState
from broker.models import OrderBase, Symbol, AssetType, OrderResult, OrderStatus


@pytest.fixture
def mock_brokers():
    kalshi = MagicMock()
    poly = MagicMock()

    # Mock for preflight slippage check
    poly.market_data = MagicMock()
    poly.market_data.ds = MagicMock()
    poly.market_data.ds.get_live_quote = AsyncMock(return_value=60)

    return {"kalshi": kalshi, "polymarket": poly}


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

    leg_a = ArbLeg(
        broker_id="kalshi",
        order=OrderBase(
            symbol=symbol_a, side="BUY", quantity=Decimal("10"), account_id="U123"
        ),
    )
    leg_b = ArbLeg(
        broker_id="polymarket",
        order=OrderBase(
            symbol=symbol_b, side="SELL", quantity=Decimal("10"), account_id="U123"
        ),
    )

    return ArbTrade(
        id="arb-123",
        symbol_a="K-1",
        symbol_b="P-1",
        leg_a=leg_a,
        leg_b=leg_b,
        expected_profit_bps=50,
    )


@pytest.mark.asyncio
async def test_arb_concurrent_success(
    mock_brokers, mock_store, mock_settings, sample_trade
):
    coordinator = ArbCoordinator(mock_brokers, mock_store, mock_settings)

    # Mock successful fills
    res_a = OrderResult(
        order_id="ext-a",
        status=OrderStatus.FILLED,
        avg_fill_price=Decimal("0.5"),
        filled_quantity=Decimal("10"),
    )
    res_b = OrderResult(
        order_id="ext-b",
        status=OrderStatus.FILLED,
        avg_fill_price=Decimal("0.6"),
        filled_quantity=Decimal("10"),
    )

    # Slow down one leg to ensure gather works
    async def slow_fill(*args, **kwargs):
        await asyncio.sleep(0.1)
        return res_b

    mock_brokers["kalshi"].orders.place_order = AsyncMock(return_value=res_a)
    mock_brokers["polymarket"].orders.place_order = AsyncMock(side_effect=slow_fill)

    success = await coordinator.execute_arbitrage(sample_trade)

    assert success
    # Verify CONCURRENT_PENDING state was hit
    states = [call.args[1] for call in mock_store.update_trade_state.call_args_list]
    assert ArbState.CONCURRENT_PENDING in states
    assert ArbState.COMPLETED in states

    # Verify update_leg_atomic was called for both legs
    assert mock_store.update_leg_atomic.call_count == 2


@pytest.mark.asyncio
async def test_arb_concurrent_partial_failure_unwind(
    mock_brokers, mock_store, mock_settings, sample_trade
):
    coordinator = ArbCoordinator(mock_brokers, mock_store, mock_settings)

    # Leg A fills, Leg B fails
    res_a = OrderResult(
        order_id="ext-a",
        status=OrderStatus.FILLED,
        avg_fill_price=Decimal("0.5"),
        filled_quantity=Decimal("10"),
    )

    mock_brokers["kalshi"].orders.place_order = AsyncMock(return_value=res_a)
    mock_brokers["polymarket"].orders.place_order = AsyncMock(
        side_effect=Exception("API Error")
    )

    success = await coordinator.execute_arbitrage(sample_trade)

    assert not success
    # Verify UNWINDING state was hit
    states = [call.args[1] for call in mock_store.update_trade_state.call_args_list]
    assert ArbState.UNWINDING in states

    # Verify Leg A was unwound
    # The first call to kalshi.orders.place_order is for leg A fill, second is for unwind
    assert mock_brokers["kalshi"].orders.place_order.call_count == 2
    unwind_order = mock_brokers["kalshi"].orders.place_order.call_args_list[1].args[1]
    assert unwind_order.side == "SELL"  # Original was BUY
    assert unwind_order.quantity == Decimal("10")


@pytest.mark.asyncio
async def test_arb_concurrent_dual_failure(
    mock_brokers, mock_store, mock_settings, sample_trade
):
    coordinator = ArbCoordinator(mock_brokers, mock_store, mock_settings)

    mock_brokers["kalshi"].orders.place_order = AsyncMock(
        side_effect=Exception("API A Error")
    )
    mock_brokers["polymarket"].orders.place_order = AsyncMock(
        side_effect=Exception("API B Error")
    )

    success = await coordinator.execute_arbitrage(sample_trade)

    assert not success
    states = [call.args[1] for call in mock_store.update_trade_state.call_args_list]
    assert ArbState.FAILED in states
    # Should NOT hit UNWINDING since both failed
    assert ArbState.UNWINDING not in states


@pytest.mark.asyncio
async def test_preflight_slippage_abort(
    mock_brokers, mock_store, mock_settings, sample_trade
):
    coordinator = ArbCoordinator(mock_brokers, mock_store, mock_settings)

    # Mock missing quote
    mock_brokers["polymarket"].market_data.ds.get_live_quote.return_value = None

    success = await coordinator.execute_arbitrage(sample_trade)

    assert not success
    # Should fail before saving trade to store if it checks slippage first
    assert not mock_store.save_trade.called
