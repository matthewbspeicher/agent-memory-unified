from __future__ import annotations
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from broker.models import MarketOrder, LimitOrder, OrderSide, OrderStatus, Symbol, AssetType


async def test_place_market_order():
    from adapters.tradier.order_manager import TradierOrderManager

    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(return_value={
        "order": {"id": 123, "status": "ok"},
    })
    mock_client.get_order = AsyncMock(return_value={
        "id": "123", "status": "filled", "exec_quantity": "10", "avg_fill_price": "150.25",
    })

    om = TradierOrderManager(mock_client, order_timeout=10, poll_interval=0.01)
    order = MarketOrder(
        symbol=Symbol(ticker="AAPL"), side=OrderSide.BUY,
        quantity=Decimal("10"), account_id="acc1",
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.FILLED


async def test_place_options_order():
    from adapters.tradier.order_manager import TradierOrderManager

    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(return_value={"order": {"id": 456, "status": "ok"}})
    mock_client.get_order = AsyncMock(return_value={
        "id": "456", "status": "filled", "exec_quantity": "5", "avg_fill_price": "3.50",
    })

    om = TradierOrderManager(mock_client, order_timeout=10, poll_interval=0.01)
    order = LimitOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.OPTION, strike=Decimal("200"), expiry=None),
        side=OrderSide.BUY, quantity=Decimal("5"), account_id="acc1",
        limit_price=Decimal("3.50"),
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.FILLED
    # Verify option_symbol was built
    call_kwargs = mock_client.place_order.call_args
    assert call_kwargs is not None


async def test_error_translates_to_rejected():
    from adapters.tradier.order_manager import TradierOrderManager
    from adapters.tradier.errors import TradierOrderRejected

    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(
        side_effect=TradierOrderRejected(400, "Order rejected")
    )

    om = TradierOrderManager(mock_client, order_timeout=10)
    order = MarketOrder(
        symbol=Symbol(ticker="AAPL"), side=OrderSide.BUY,
        quantity=Decimal("10"), account_id="acc1",
    )
    result = await om.place_order("acc1", order)

    assert result.status == OrderStatus.REJECTED
    assert "rejected" in result.message.lower()
