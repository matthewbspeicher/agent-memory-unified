from __future__ import annotations
import asyncio
import logging
from typing import Any

import httpx

from adapters.alpaca.errors import (
    AlpacaAPIError,
    AlpacaForbidden,
    AlpacaInsufficientFunds,
    AlpacaOrderRejected,
    AlpacaRateLimited,
    AlpacaAssetNotTradeable,
)

logger = logging.getLogger(__name__)

_RETRY_BACKOFF = [1.0, 2.0, 4.0]  # seconds


class AlpacaClient:
    """Async REST client for Alpaca Trading and Market Data APIs.

    Maintains two httpx.AsyncClient instances:
    - _trading_client → paper-api.alpaca.markets or api.alpaca.markets
    - _data_client → data.alpaca.markets
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        data_feed: str = "iex",
        timeout: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._paper = paper
        self._data_feed = data_feed
        self._timeout = timeout
        self._trading_base_url = (
            "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        )
        self._data_base_url = "https://data.alpaca.markets"
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }
        self._data_params: dict[str, str] = {"feed": data_feed}
        self._trading_http: httpx.AsyncClient | None = None
        self._data_http: httpx.AsyncClient | None = None

    async def open(self) -> None:
        """Create httpx client instances."""
        self._trading_http = httpx.AsyncClient(
            base_url=self._trading_base_url,
            headers=self._headers,
            timeout=self._timeout,
        )
        self._data_http = httpx.AsyncClient(
            base_url=self._data_base_url,
            headers=self._headers,
            timeout=self._timeout,
        )

    async def close(self) -> None:
        """Close httpx client instances."""
        if self._trading_http:
            await self._trading_http.aclose()
            self._trading_http = None
        if self._data_http:
            await self._data_http.aclose()
            self._data_http = None

    # -- Internal request helpers --

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Trading API request with retry on 429."""
        if not self._trading_http:
            raise RuntimeError("Client not open — call open() first")
        return await self._do_request(self._trading_http, method, path, **kwargs)

    async def _data_request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Data API request with retry on 429 and feed param."""
        if not self._data_http:
            raise RuntimeError("Client not open — call open() first")
        params = {**self._data_params, **kwargs.pop("params", {})}
        return await self._do_request(self._data_http, method, path, params=params, **kwargs)

    async def _do_request(
        self, http: httpx.AsyncClient, method: str, path: str, **kwargs: Any,
    ) -> Any:
        for attempt, backoff in enumerate(_RETRY_BACKOFF + [0]):
            resp = await http.request(method, path, **kwargs)
            if resp.status_code == 429:
                if attempt < len(_RETRY_BACKOFF):
                    logger.warning("Alpaca 429 rate limited, retrying in %.1fs", backoff)
                    await asyncio.sleep(backoff)
                    continue
                raise AlpacaRateLimited(429, "Rate limit exceeded after retries")
            break

        if resp.status_code == 403:
            body = resp.json() if resp.content else {}
            raise AlpacaForbidden(403, body.get("message", "Forbidden"))
        if resp.status_code == 422:
            body = resp.json() if resp.content else {}
            code = body.get("code", 422)
            msg = body.get("message", "Unprocessable")
            if "buying power" in msg.lower() or "insufficient" in msg.lower():
                raise AlpacaInsufficientFunds(code, msg)
            if "not tradable" in msg.lower() or "halted" in msg.lower():
                raise AlpacaAssetNotTradeable(code, msg)
            raise AlpacaOrderRejected(code, msg)

        resp.raise_for_status()
        return resp.json()

    # -- Account --

    async def get_account(self) -> dict[str, Any]:
        return await self._request("GET", "/v2/account")

    async def get_positions(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/v2/positions")

    async def get_orders(self, status: str = "all") -> list[dict[str, Any]]:
        return await self._request("GET", "/v2/orders", params={"status": status})

    # -- Trading --

    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str,
        time_in_force: str,
        limit_price: float | None = None,
        stop_price: float | None = None,
        trail_percent: float | None = None,
        trail_price: float | None = None,
        order_class: str | None = None,
        take_profit: dict | None = None,
        stop_loss: dict | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if limit_price is not None:
            body["limit_price"] = str(limit_price)
        if stop_price is not None:
            body["stop_price"] = str(stop_price)
        if trail_percent is not None:
            body["trail_percent"] = str(trail_percent)
        if trail_price is not None:
            body["trail_price"] = str(trail_price)
        if order_class is not None:
            body["order_class"] = order_class
        if take_profit is not None:
            body["take_profit"] = take_profit
        if stop_loss is not None:
            body["stop_loss"] = stop_loss
        return await self._request("POST", "/v2/orders", json=body)

    async def cancel_order(self, order_id: str) -> None:
        await self._request("DELETE", f"/v2/orders/{order_id}")

    async def cancel_all_orders(self) -> None:
        await self._request("DELETE", "/v2/orders")

    async def get_order(self, order_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/orders/{order_id}")

    # -- Market Data --

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        return await self._data_request("GET", f"/v2/stocks/{symbol}/quotes/latest")

    async def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        return await self._data_request(
            "GET", "/v2/stocks/quotes/latest", params={"symbols": ",".join(symbols)},
        )

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: str,
        end: str,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        """Fetch bars with automatic pagination on next_page_token."""
        all_bars: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": limit,
            }
            if page_token:
                params["page_token"] = page_token

            data = await self._data_request("GET", f"/v2/stocks/{symbol}/bars", params=params)
            bars = data.get("bars", [])
            all_bars.extend(bars)

            page_token = data.get("next_page_token")
            if not page_token:
                break

        return all_bars

    async def get_snapshot(self, symbol: str) -> dict[str, Any]:
        return await self._data_request("GET", f"/v2/stocks/{symbol}/snapshot")

    # -- Utility --

    async def get_clock(self) -> dict[str, Any]:
        return await self._request("GET", "/v2/clock")

    async def get_asset(self, symbol: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/assets/{symbol}")
