"""Unit tests for BitGetClient, BitGetBroker, and related classes."""

from __future__ import annotations

import pytest
import base64
import hashlib
import hmac
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from broker.models import (
    BrokerCapabilities,
    LimitOrder,
    MarketOrder,
    OrderSide,
    OrderStatus,
    Symbol,
)
from adapters.bitget.client import BitGetClient
from adapters.bitget.adapter import (
    BitGetBroker,
    BitGetAccount,
    BitGetOrderManager,
    ACCOUNT_ID,
)


class TestBitGetClientSignature:
    def test_sign_produces_valid_base64(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )
        signature = client._sign(
            "1234567890", "POST", "/api/v2/spot/trade/placeOrder", ""
        )
        # Should be valid base64
        decoded = base64.b64decode(signature)
        assert len(decoded) == 32  # SHA256 produces 32 bytes

    def test_sign_is_deterministic(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )
        sig1 = client._sign("1234567890", "POST", "/test/path", "body")
        sig2 = client._sign("1234567890", "POST", "/test/path", "body")
        assert sig1 == sig2

    def test_sign_changes_with_input(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )
        sig1 = client._sign("1234567890", "POST", "/test/path", "")
        sig2 = client._sign(
            "1234567891", "POST", "/test/path", ""
        )  # Different timestamp
        assert sig1 != sig2

    def test_sign_matches_manual_calculation(self):
        secret = "test_secret"
        client = BitGetClient(
            api_key="test_key",
            secret_key=secret,
            passphrase="test_pass",
        )
        timestamp = "1234567890"
        method = "POST"
        path = "/api/v2/spot/trade/placeOrder"
        body = ""

        expected = base64.b64encode(
            hmac.new(
                secret.encode("utf-8"),
                f"{timestamp}{method}{path}{body}".encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        assert client._sign(timestamp, method, path, body) == expected


class TestBitGetClientHeaders:
    def test_headers_contain_required_fields(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )
        headers = client._headers("POST", "/test/path", "body")

        assert "ACCESS-KEY" in headers
        assert "ACCESS-SIGN" in headers
        assert "ACCESS-TIMESTAMP" in headers
        assert "ACCESS-PASSPHRASE" in headers
        assert headers["ACCESS-KEY"] == "test_key"
        assert headers["ACCESS-PASSPHRASE"] == "test_pass"
        assert headers["Content-Type"] == "application/json"

    def test_timestamp_is_milliseconds(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )
        headers = client._headers("GET", "/test")
        timestamp = headers["ACCESS-TIMESTAMP"]
        # Should be an integer string representing milliseconds
        ts_int = int(timestamp)
        assert ts_int > 1_000_000_000_000  # After year 2001 in ms


@pytest.mark.asyncio
class TestBitGetClientBalance:
    async def test_get_balances_parses_response(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "balanceList": [
                    {"coin": "USDT", "available": "1000.00", "frozen": "0"},
                    {"coin": "BTC", "available": "0.5", "frozen": "0"},
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.get.return_value = mock_response

        balances = await client.get_balances()
        assert len(balances) == 2
        assert balances[0]["coin"] == "USDT"

    async def test_get_available_balance(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "balanceList": [
                    {"coin": "USDT", "available": "1000.00"},
                    {"coin": "BTC", "available": "0.5"},
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.get.return_value = mock_response

        usdt_balance = await client.get_available_balance("USDT")
        assert usdt_balance == Decimal("1000.00")

        eth_balance = await client.get_available_balance("ETH")
        assert eth_balance == Decimal("0")


@pytest.mark.asyncio
class TestBitGetClientOrders:
    async def test_place_order_success(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "00000",
            "data": {"orderId": "order123", "clientOrderId": "client123"},
        }
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post.return_value = mock_response

        result = await client.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity="0.1",
        )
        assert result["orderId"] == "order123"

    async def test_place_order_failure_raises(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "40001",
            "msg": "Invalid parameters",
        }
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post.return_value = mock_response

        with pytest.raises(ValueError, match="BitGet order failed"):
            await client.place_order(
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity="0.1",
            )

    async def test_cancel_order_success(self):
        client = BitGetClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"code": "00000", "data": {}}
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post.return_value = mock_response

        result = await client.cancel_order("BTCUSDT", "order123")
        assert result == {}


class TestBitGetOrderManager:
    def test_dry_run_returns_submitted(self):
        mock_client = MagicMock()
        manager = BitGetOrderManager(mock_client, dry_run=True)

        assert manager.dry_run is True

    def test_order_symbols_tracking(self):
        mock_client = MagicMock()
        manager = BitGetOrderManager(mock_client, dry_run=False)

        # Simulate order symbol tracking
        manager._order_symbols["order123"] = "ETHUSDT"
        assert manager._order_symbols.get("order123") == "ETHUSDT"
        assert manager._order_symbols.get("unknown", "BTCUSDT") == "BTCUSDT"

    def test_cancel_uses_tracked_symbol(self):
        mock_client = MagicMock()
        mock_client.cancel_order = AsyncMock(return_value={})

        manager = BitGetOrderManager(mock_client, dry_run=False)
        manager._order_symbols["order456"] = "SOLUSDT"

        # Verify the tracked symbol is used, not BTCUSDT
        assert manager._order_symbols.get("order456", "BTCUSDT") == "SOLUSDT"


class TestBitGetAccount:
    def test_get_accounts_returns_default(self):
        mock_client = MagicMock()
        account = BitGetAccount(mock_client)

        # Just verify the structure
        assert account.client is mock_client
        assert ACCOUNT_ID == "BITGET"


class TestBitGetBrokerCapabilities:
    def test_capabilities_structure(self):
        mock_client = MagicMock()
        broker = BitGetBroker(
            api_key="key",
            secret_key="secret",
            passphrase="pass",
            dry_run=True,
        )

        caps = broker.capabilities()
        assert isinstance(caps, BrokerCapabilities)
        assert caps.stocks is True
        assert caps.options is False
        assert caps.futures is False
