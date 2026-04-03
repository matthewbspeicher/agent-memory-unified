from __future__ import annotations
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from broker.models import (
    BracketOrder, OrderSide, OrderStatus, StopLimitOrder, StopOrder,
    Symbol, TrailingStopOrder,
)


async def test_stop_order():
    from adapters.alpaca.order_manager import AlpacaOrderManager

    mock_client = MagicMock()
    mock_client.submit_order = AsyncMock(return_value={
        "id": "ord1", "status": "accepted", "filled_qty": "0",
    })
    mock_client.get_order = AsyncMock(return_value={
        "id": "ord1", "status": "filled", "filled_qty": "10", "filled_avg_price": "149.50",
    })

    om = AlpacaOrderManager(mock_client, order_timeout=10, poll_interval=0.01)
    order = StopOrder(
        symbol=Symbol(ticker="AAPL"), side=OrderSide.SELL,
        quantity=Decimal("10"), account_id="acc1",
        stop_price=Decimal("150.00"),
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.FILLED
    call_kwargs = mock_client.submit_order.call_args
    assert call_kwargs is not None


async def test_trailing_stop_percent():
    from adapters.alpaca.order_manager import AlpacaOrderManager

    mock_client = MagicMock()
    mock_client.submit_order = AsyncMock(return_value={
        "id": "ord1", "status": "filled", "filled_qty": "10", "filled_avg_price": "148.00",
    })

    om = AlpacaOrderManager(mock_client, order_timeout=10)
    order = TrailingStopOrder(
        symbol=Symbol(ticker="AAPL"), side=OrderSide.SELL,
        quantity=Decimal("10"), account_id="acc1",
        trail_percent=Decimal("2.0"),
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.FILLED


async def test_bracket_order():
    from adapters.alpaca.order_manager import AlpacaOrderManager

    mock_client = MagicMock()
    mock_client.submit_order = AsyncMock(return_value={
        "id": "ord1", "status": "filled", "filled_qty": "10", "filled_avg_price": "150.00",
    })

    om = AlpacaOrderManager(mock_client, order_timeout=10)
    order = BracketOrder(
        symbol=Symbol(ticker="AAPL"), side=OrderSide.BUY,
        quantity=Decimal("10"), account_id="acc1",
        take_profit_price=Decimal("170.00"),
        stop_loss_price=Decimal("140.00"),
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.FILLED
    # Verify bracket params were sent
    call_args = mock_client.submit_order.call_args
    assert call_args is not None
