from __future__ import annotations
import asyncio
import logging
from typing import Any

import httpx

from adapters.tradier.errors import (
    TradierAPIError,
    TradierInvalidSymbol,
    TradierOrderRejected,
    TradierRateLimited,
)

logger = logging.getLogger(__name__)

_RETRY_BACKOFF = [1.0, 2.0, 4.0]


class TradierClient:
    """Async REST client for Tradier API."""

    def __init__(
        self,
        token: str,
        account_id: str,
        sandbox: bool = True,
        timeout: float = 15.0,
    ) -> None:
        self._token = token
        self._account_id = account_id
        self._sandbox = sandbox
        self._timeout = timeout
        self._base_url = (
            "https://sandbox.tradier.com" if sandbox else "https://api.tradier.com"
        )
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        self._http: httpx.AsyncClient | None = None

    async def open(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout,
        )

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    @property
    def account_id(self) -> str:
        return self._account_id

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._http:
            raise RuntimeError("Client not open — call open() first")

        for attempt, backoff in enumerate(_RETRY_BACKOFF + [0]):
            resp = await self._http.request(method, path, **kwargs)
            if resp.status_code == 429:
                if attempt < len(_RETRY_BACKOFF):
                    logger.warning(
                        "Tradier 429 rate limited, retrying in %.1fs", backoff
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise TradierRateLimited(429, "Rate limit exceeded after retries")
            break

        if resp.status_code == 400:
            body = resp.json() if resp.content else {}
            fault = body.get("fault", {}).get("faultstring", "Bad request")
            raise TradierOrderRejected(400, fault)
        if resp.status_code == 401:
            raise TradierAPIError(401, "Unauthorized — check API token")
        if resp.status_code == 404:
            raise TradierInvalidSymbol(404, "Symbol or resource not found")

        resp.raise_for_status()
        return resp.json()

    # -- Account --

    async def get_profile(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/user/profile")

    async def get_balances(self) -> dict[str, Any]:
        return await self._request("GET", f"/v1/accounts/{self._account_id}/balances")

    async def get_positions(self) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/v1/accounts/{self._account_id}/positions")
        positions = data.get("positions", {})
        if positions == "null" or positions is None:
            return []
        pos_list = positions.get("position", [])
        return pos_list if isinstance(pos_list, list) else [pos_list]

    async def get_orders(self, status: str = "all") -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/v1/accounts/{self._account_id}/orders",
        )
        orders = data.get("orders", {})
        if orders == "null" or orders is None:
            return []
        order_list = orders.get("order", [])
        return order_list if isinstance(order_list, list) else [order_list]

    # -- Trading --

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
        duration: str,
        price: float | None = None,
        stop: float | None = None,
        option_symbol: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "class": "option" if option_symbol else "equity",
            "symbol": symbol,
            "side": side,
            "quantity": str(qty),
            "type": order_type,
            "duration": duration,
        }
        if price is not None:
            data["price"] = str(price)
        if stop is not None:
            data["stop"] = str(stop)
        if option_symbol:
            data["option_symbol"] = option_symbol
        return await self._request(
            "POST",
            f"/v1/accounts/{self._account_id}/orders",
            data=data,
        )

    async def cancel_order(self, order_id: str) -> None:
        await self._request("PUT", f"/v1/accounts/{self._account_id}/orders/{order_id}")

    async def get_order(self, order_id: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/v1/accounts/{self._account_id}/orders/{order_id}",
        )
        return data.get("order", data)

    # -- Market Data --

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        return await self._request(
            "GET", "/v1/markets/quotes", params={"symbols": symbol}
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v1/markets/quotes",
            params={"symbols": ",".join(symbols)},
        )

    async def get_historical(
        self,
        symbol: str,
        interval: str,
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/v1/markets/history",
            params={"symbol": symbol, "interval": interval, "start": start, "end": end},
        )
        history = data.get("history", {})
        if history is None or history == "null":
            return []
        day_list = history.get("day", [])
        return day_list if isinstance(day_list, list) else [day_list]

    async def get_options_chain(self, symbol: str, expiration: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v1/markets/options/chains",
            params={"symbol": symbol, "expiration": expiration, "greeks": "true"},
        )

    async def get_options_expirations(self, symbol: str) -> list[str]:
        data = await self._request(
            "GET",
            "/v1/markets/options/expirations",
            params={"symbol": symbol},
        )
        exps = data.get("expirations", {})
        if exps is None:
            return []
        date_list = exps.get("date", [])
        return date_list if isinstance(date_list, list) else [date_list]

    async def get_clock(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/markets/clock")

    async def cancel_all_orders(self) -> None:
        orders = await self.get_orders(status="pending")
        for order in orders:
            try:
                await self.cancel_order(str(order.get("id", "")))
            except Exception as e:
                logger.warning("Failed to cancel order %s: %s", order.get("id"), e)
