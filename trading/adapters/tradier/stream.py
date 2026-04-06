from __future__ import annotations
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal

import httpx

from broker.models import Quote, Symbol
from streaming.base import BrokerStream

logger = logging.getLogger(__name__)

_BACKOFF = [1, 2, 4, 8, 16, 30]


class TradierStream(BrokerStream):
    """Tradier real-time quote stream via SSE."""

    def __init__(self, token: str, sandbox: bool = True) -> None:
        self._token = token
        self._base_url = (
            "https://sandbox.tradier.com" if sandbox else "https://stream.tradier.com"
        )
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        self._connected = False
        self._subscribed_symbols: set[str] = set()
        self._callbacks: list[Callable[[str, Quote], Awaitable[None]]] = []
        self._session_url: str | None = None
        self._session_id: str | None = None
        self._sse_task: asyncio.Task | None = None
        self._disconnect_callbacks: list[Callable[[], None]] = []

    async def connect(self) -> None:
        # Create streaming session
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self._base_url}/v1/markets/events/session",
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
            stream_data = data.get("stream", {})
            self._session_url = stream_data.get("url")
            self._session_id = stream_data.get("sessionid")

        if not self._session_url:
            raise ConnectionError("Failed to create Tradier streaming session")

        self._connected = True
        logger.info("TradierStream session created")

    async def disconnect(self) -> None:
        self._connected = False
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
            self._sse_task = None

    async def subscribe(self, symbols: list[str]) -> None:
        self._subscribed_symbols.update(symbols)
        if self._connected:
            await self._restart_sse()

    async def unsubscribe(self, symbols: list[str]) -> None:
        self._subscribed_symbols -= set(symbols)
        if self._connected and self._subscribed_symbols:
            await self._restart_sse()

    def is_connected(self) -> bool:
        return self._connected

    def on_quote(self, callback: Callable[[str, Quote], Awaitable[None]]) -> None:
        self._callbacks.append(callback)

    async def reconnect(self) -> None:
        await self.disconnect()
        await self.connect()
        if self._subscribed_symbols:
            await self.subscribe(list(self._subscribed_symbols))

    def on_disconnected(self, callback: Callable[[], None]) -> None:
        self._disconnect_callbacks.append(callback)

    async def _restart_sse(self) -> None:
        """(Re)start the SSE listener with current subscriptions."""
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
        self._sse_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        """SSE listener loop."""
        if not self._session_url or not self._subscribed_symbols:
            return

        symbols_param = ",".join(self._subscribed_symbols)
        url = (
            f"{self._session_url}?sessionid={self._session_id}&symbols={symbols_param}"
        )

        try:
            from httpx_sse import aconnect_sse

            async with httpx.AsyncClient(timeout=None) as client:
                async with aconnect_sse(
                    client, "GET", url, headers=self._headers
                ) as event_source:
                    async for event in event_source.aiter_sse():
                        if event.data:
                            try:
                                data = json.loads(event.data)
                                if data.get("type") == "quote":
                                    await self._handle_quote(data)
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            self._connected = False
            logger.warning("TradierStream disconnected: %s", e)
            for cb in self._disconnect_callbacks:
                try:
                    cb()
                except Exception:
                    pass
            await self._auto_reconnect()

    async def _handle_quote(self, data: dict) -> None:
        symbol = data.get("symbol", "")
        quote = Quote(
            symbol=Symbol(ticker=symbol),
            bid=Decimal(str(data.get("bid", 0))) if data.get("bid") else None,
            ask=Decimal(str(data.get("ask", 0))) if data.get("ask") else None,
            last=Decimal(str(data.get("last", 0))) if data.get("last") else None,
            volume=data.get("cumulative_volume", 0),
        )
        for cb in self._callbacks:
            try:
                await cb(symbol, quote)
            except Exception as e:
                logger.warning("TradierStream callback error: %s", e)

    async def _auto_reconnect(self) -> None:
        for delay in _BACKOFF:
            try:
                logger.info("TradierStream reconnecting in %ds", delay)
                await asyncio.sleep(delay)
                await self.reconnect()
                return
            except Exception as e:
                logger.warning("TradierStream reconnect failed: %s", e)
        logger.error("TradierStream gave up reconnecting")
