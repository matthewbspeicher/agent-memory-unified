"""
BitGet Client wrapper.

Handles REST API authentication (HMAC-SHA256 signature) and endpoints
for spot trading, account balance, and order management.
Reference: https://bitget.github.io/docs/api/spot/v2
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL_SPOT = "https://api.bitget.com"


class BitGetClient:
    """BitGet REST API client with HMAC-SHA256 signature authentication."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        base_url: str = BASE_URL_SPOT,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    # ------------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------------

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate HMAC-SHA256 signature for BitGet API."""
        import base64

        message = f"{timestamp}{method}{path}{body}"
        return base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

    def _headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        """Build request headers with authentication."""
        timestamp = str(int(time.time() * 1000))
        signature = self._sign(timestamp, method, path, body)
        return {
            "Content-Type": "application/json",
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
        }

    # ------------------------------------------------------------------------
    # Account Endpoints
    # ------------------------------------------------------------------------

    async def get_account_balance(self) -> dict[str, Any]:
        """Fetch account balance (spot)."""
        path = "/api/v2/spot/account/balance"
        headers = self._headers("GET", path)
        resp = await self._client.get(f"{self.base_url}{path}", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def get_balances(self) -> list[dict[str, Any]]:
        """Get all asset balances."""
        data = await self.get_account_balance()
        return data.get("data", {}).get("balanceList", [])

    async def get_available_balance(self, currency: str) -> Decimal:
        """Get available balance for a specific currency."""
        balances = await self.get_balances()
        for bal in balances:
            if bal.get("coin") == currency.upper():
                return Decimal(bal.get("available", "0"))
        return Decimal("0")

    # ------------------------------------------------------------------------
    # Order Endpoints
    # ------------------------------------------------------------------------

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        price: str | None = None,
    ) -> dict[str, Any]:
        """
        Place a spot order.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: "buy" or "sell"
            order_type: "market" or "limit"
            quantity: Order quantity
            price: Limit price (required for limit orders)

        Returns:
            Order response with order_id
        """
        path = "/api/v2/spot/trade/placeOrder"

        body = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "quantity": quantity,
        }

        if price and order_type == "limit":
            body["price"] = price

        body_str = str(body)
        headers = self._headers("POST", path, body_str)

        resp = await self._client.post(
            f"{self.base_url}{path}",
            headers=headers,
            content=body_str,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != "00000":
            raise ValueError(f"BitGet order failed: {data.get('msg', 'Unknown error')}")

        return data.get("data", {})

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Cancel an existing order."""
        path = "/api/v2/spot/trade/cancelOrder"
        body = {"symbol": symbol, "orderId": order_id}
        body_str = str(body)
        headers = self._headers("POST", path, body_str)

        resp = await self._client.post(
            f"{self.base_url}{path}",
            headers=headers,
            content=body_str,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != "00000":
            raise ValueError(
                f"BitGet cancel failed: {data.get('msg', 'Unknown error')}"
            )

        return data.get("data", {})

    async def get_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Get order details."""
        path = "/api/v2/spot/trade/orderInfo"
        body = {"symbol": symbol, "orderId": order_id}
        body_str = str(body)
        headers = self._headers("POST", path, body_str)

        resp = await self._client.post(
            f"{self.base_url}{path}",
            headers=headers,
            content=body_str,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_positions(self) -> list[dict[str, Any]]:
        """Get current positions (spot assets with non-zero balance)."""
        path = "/api/v2/spot/account/assets"
        headers = self._headers("GET", path)

        resp = await self._client.get(
            f"{self.base_url}{path}",
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Get all open orders."""
        path = "/api/v2/spot/trade/openOrders"
        body = {"symbol": symbol} if symbol else {}
        body_str = str(body)
        headers = self._headers("POST", path, body_str)

        resp = await self._client.post(
            f"{self.base_url}{path}",
            headers=headers,
            content=body_str,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def get_order_history(
        self, symbol: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get historical orders."""
        path = "/api/v2/spot/trade/historyOrders"
        body = {"symbol": symbol, "limit": limit}
        body_str = str(body)
        headers = self._headers("POST", path, body_str)

        resp = await self._client.post(
            f"{self.base_url}{path}",
            headers=headers,
            content=body_str,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    # ------------------------------------------------------------------------
    # Market Data (Public endpoints - no auth required)
    # ------------------------------------------------------------------------

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get current ticker price."""
        resp = await self._client.get(
            f"{self.base_url}/api/v2/spot/market/ticker",
            params={"symbol": symbol},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {})

    async def get_klines(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> list[list[Any]]:
        """
        Get candlestick/kline data.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            timeframe: "1m", "5m", "15m", "1h", "4h", "1d", "1w"
            limit: Number of candles (max 2000)

        Returns:
            List of [timestamp, open, high, low, close, volume]
        """
        resp = await self._client.get(
            f"{self.base_url}/api/v2/spot/market/klines",
            params={
                "symbol": symbol,
                "type": timeframe,
                "limit": limit,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def get_all_tickers(self) -> list[dict[str, Any]]:
        """Get all ticker prices (24h)."""
        resp = await self._client.get(
            f"{self.base_url}/api/v2/spot/market/tickers",
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    # ------------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BitGetClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
