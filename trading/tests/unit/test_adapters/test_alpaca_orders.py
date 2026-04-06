from __future__ import annotations
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock


from broker.models import MarketOrder, OrderSide, OrderStatus, Symbol


async def test_place_market_order_filled_immediately():
    from adapters.alpaca.order_manager import AlpacaOrderManager

    mock_client = MagicMock()
    mock_client.submit_order = AsyncMock(
        return_value={
            "id": "ord1",
            "status": "filled",
            "filled_qty": "10",
            "filled_avg_price": "150.25",
        }
    )

    om = AlpacaOrderManager(mock_client, order_timeout=10)
    order = MarketOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="acc1",
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == Decimal("10")
    assert result.avg_fill_price == Decimal("150.25")
    # Should NOT poll — already terminal
    mock_client.get_order.assert_not_called()


async def test_place_order_polls_until_filled():
    from adapters.alpaca.order_manager import AlpacaOrderManager

    mock_client = MagicMock()
    mock_client.submit_order = AsyncMock(
        return_value={
            "id": "ord1",
            "status": "accepted",
            "filled_qty": "0",
        }
    )
    mock_client.get_order = AsyncMock(
        side_effect=[
            {
                "id": "ord1",
                "status": "partially_filled",
                "filled_qty": "5",
                "filled_avg_price": "150.0",
            },
            {
                "id": "ord1",
                "status": "filled",
                "filled_qty": "10",
                "filled_avg_price": "150.25",
            },
        ]
    )

    om = AlpacaOrderManager(mock_client, order_timeout=10, poll_interval=0.01)
    order = MarketOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="acc1",
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.FILLED
    assert mock_client.get_order.call_count == 2


async def test_place_order_timeout_cancels():
    from adapters.alpaca.order_manager import AlpacaOrderManager

    mock_client = MagicMock()
    mock_client.submit_order = AsyncMock(
        return_value={
            "id": "ord1",
            "status": "accepted",
            "filled_qty": "0",
        }
    )
    mock_client.get_order = AsyncMock(
        return_value={
            "id": "ord1",
            "status": "accepted",
            "filled_qty": "0",
        }
    )
    mock_client.cancel_order = AsyncMock()

    om = AlpacaOrderManager(mock_client, order_timeout=0.05, poll_interval=0.01)
    order = MarketOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="acc1",
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.CANCELLED
    mock_client.cancel_order.assert_called_once_with("ord1")


async def test_error_translates_to_rejected():
    from adapters.alpaca.order_manager import AlpacaOrderManager
    from adapters.alpaca.errors import AlpacaInsufficientFunds

    mock_client = MagicMock()
    mock_client.submit_order = AsyncMock(
        side_effect=AlpacaInsufficientFunds(40310000, "insufficient buying power")
    )

    om = AlpacaOrderManager(mock_client, order_timeout=10)
    order = MarketOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="acc1",
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.REJECTED
    assert "insufficient" in result.message.lower()
