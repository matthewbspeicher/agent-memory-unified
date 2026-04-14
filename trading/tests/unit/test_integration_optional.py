"""Integration tests for new features: achievements, arbitrage, BitGet."""

from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from broker.models import OrderStatus, Symbol, AssetType


class TestBitGetPositionTracking:
    async def test_get_positions_returns_empty_for_zero_balances(self):
        from adapters.bitget.adapter import BitGetAccount, ACCOUNT_ID

        mock_client = AsyncMock()
        mock_client.get_positions.return_value = [
            {"coin": "BTC", "available": "0", "frozen": "0"},
            {"coin": "USDT", "available": "0", "frozen": "0"},
        ]

        account = BitGetAccount(mock_client)
        positions = await account.get_positions(ACCOUNT_ID)

        assert positions == []

    async def test_get_positions_filters_nonzero_balances(self):
        from adapters.bitget.adapter import BitGetAccount, ACCOUNT_ID

        mock_client = AsyncMock()
        mock_client.get_positions.return_value = [
            {"coin": "BTC", "available": "0.5", "frozen": "0"},
            {"coin": "USDT", "available": "1000", "frozen": "0"},
        ]

        account = BitGetAccount(mock_client)
        positions = await account.get_positions(ACCOUNT_ID)

        assert len(positions) == 2
        assert positions[0].quantity == Decimal("0.5")
        assert positions[1].quantity == Decimal("1000")

    async def test_get_positions_handles_api_error(self):
        from adapters.bitget.adapter import BitGetAccount, ACCOUNT_ID

        mock_client = AsyncMock()
        mock_client.get_positions.side_effect = Exception("API Error")

        account = BitGetAccount(mock_client)
        positions = await account.get_positions(ACCOUNT_ID)

        assert positions == []


class TestBitGetOrderHistory:
    async def test_order_history_with_symbol(self):
        from adapters.bitget.adapter import BitGetAccount, ACCOUNT_ID
        from broker.models import OrderHistoryFilter

        mock_client = AsyncMock()
        mock_client.get_order_history.return_value = [
            {
                "orderId": "123",
                "status": "filled",
                "fillQty": "0.1",
                "fillPrice": "50000",
            },
        ]

        account = BitGetAccount(mock_client)
        btc_symbol = Symbol(ticker="BTCUSDT", asset_type=AssetType.STOCK)
        filters = OrderHistoryFilter(symbol=btc_symbol)
        results = await account.get_order_history(ACCOUNT_ID, filters)

        assert len(results) == 1
        assert results[0].order_id == "123"
        assert results[0].status == OrderStatus.FILLED

    async def test_order_history_status_mapping(self):
        from adapters.bitget.adapter import BitGetAccount, ACCOUNT_ID

        mock_client = AsyncMock()
        mock_client.get_open_orders.return_value = [
            {"orderId": "1", "status": "new", "fillQty": "0", "fillPrice": "0"},
            {
                "orderId": "2",
                "status": "partially_filled",
                "fillQty": "0.5",
                "fillPrice": "49000",
            },
            {"orderId": "3", "status": "filled", "fillQty": "1", "fillPrice": "50000"},
            {"orderId": "4", "status": "canceled", "fillQty": "0", "fillPrice": "0"},
        ]

        account = BitGetAccount(mock_client)
        results = await account.get_order_history(ACCOUNT_ID, None)

        assert len(results) == 4
        assert results[0].status == OrderStatus.SUBMITTED
        assert results[1].status == OrderStatus.PARTIAL
        assert results[2].status == OrderStatus.FILLED
        assert results[3].status == OrderStatus.CANCELLED
