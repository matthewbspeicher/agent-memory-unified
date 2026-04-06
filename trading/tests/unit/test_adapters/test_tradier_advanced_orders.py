from __future__ import annotations
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock


from broker.models import (
    BracketOrder,
    OrderSide,
    OrderStatus,
    StopOrder,
    Symbol,
    TrailingStopOrder,
)


async def test_stop_order():
    from adapters.tradier.order_manager import TradierOrderManager

    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(
        return_value={"order": {"id": 123, "status": "ok"}}
    )
    mock_client.get_order = AsyncMock(
        return_value={
            "id": "123",
            "status": "filled",
            "exec_quantity": "10",
            "avg_fill_price": "149.50",
        }
    )

    om = TradierOrderManager(mock_client, order_timeout=10, poll_interval=0.01)
    order = StopOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.SELL,
        quantity=Decimal("10"),
        account_id="acc1",
        stop_price=Decimal("150.00"),
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.FILLED


async def test_trailing_stop_amount():
    from adapters.tradier.order_manager import TradierOrderManager

    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(
        return_value={"order": {"id": 456, "status": "ok"}}
    )
    mock_client.get_order = AsyncMock(
        return_value={
            "id": "456",
            "status": "filled",
            "exec_quantity": "10",
            "avg_fill_price": "148.00",
        }
    )

    om = TradierOrderManager(mock_client, order_timeout=10, poll_interval=0.01)
    order = TrailingStopOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.SELL,
        quantity=Decimal("10"),
        account_id="acc1",
        trail_amount=Decimal("3.00"),
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.FILLED


async def test_trailing_stop_percent_rejected():
    from adapters.tradier.order_manager import TradierOrderManager

    mock_client = MagicMock()
    om = TradierOrderManager(mock_client, order_timeout=10)
    order = TrailingStopOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.SELL,
        quantity=Decimal("10"),
        account_id="acc1",
        trail_percent=Decimal("2.0"),
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.REJECTED
    assert (
        "trail_amount" in result.message.lower() or "percent" in result.message.lower()
    )


async def test_bracket_order_rejected():
    from adapters.tradier.order_manager import TradierOrderManager

    mock_client = MagicMock()
    om = TradierOrderManager(mock_client, order_timeout=10)
    order = BracketOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="acc1",
        take_profit_price=Decimal("170"),
        stop_loss_price=Decimal("140"),
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.REJECTED
    assert (
        "deferred" in result.message.lower()
        or "not implemented" in result.message.lower()
    )
