from __future__ import annotations
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal

import websockets

from broker.models import Quote, Symbol
from streaming.base import BrokerStream

logger = logging.getLogger(__name__)

_BACKOFF = [1, 2, 4, 8, 16, 30]


class AlpacaStream(BrokerStream):
    """Alpaca real-time quote stream via WebSocket."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        data_feed: str = "iex",
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._url = f"wss://stream.data.alpaca.markets/v2/{data_feed}"
        self._ws = None
        self._connected = False
        self._subscribed_symbols: set[str] = set()
        self._callbacks: list[Callable[[str, Quote], Awaitable[None]]] = []
        self._listen_task: asyncio.Task | None = None
        self._disconnect_callbacks: list[Callable[[], None]] = []

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._url)
        # Authenticate
        auth_msg = json.dumps(
            {
                "action": "auth",
                "key": self._api_key,
                "secret": self._secret_key,
            }
        )
        await self._ws.send(auth_msg)
        await self._ws.recv()
        self._connected = True
        logger.info("AlpacaStream connected and authenticated")
        # Start listening
        self._listen_task = asyncio.create_task(self._listen())

    async def disconnect(self) -> None:
        self._connected = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def subscribe(self, symbols: list[str]) -> None:
        self._subscribed_symbols.update(symbols)
        if self._ws and self._connected:
            msg = json.dumps({"action": "subscribe", "quotes": symbols})
            await self._ws.send(msg)
            logger.debug("AlpacaStream subscribed: %s", symbols)

    async def unsubscribe(self, symbols: list[str]) -> None:
        self._subscribed_symbols -= set(symbols)
        if self._ws and self._connected:
            msg = json.dumps({"action": "unsubscribe", "quotes": symbols})
            await self._ws.send(msg)

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

    async def _listen(self) -> None:
        """Main listen loop — parse messages and invoke callbacks."""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    if isinstance(data, list):
                        for item in data:
                            if item.get("T") == "q":
                                await self._handle_quote(item)
                except Exception as e:
                    logger.debug("AlpacaStream parse error: %s", e)
        except websockets.ConnectionClosed:
            self._connected = False
            logger.warning("AlpacaStream disconnected, will reconnect")
            for cb in self._disconnect_callbacks:
                try:
                    cb()
                except Exception:
                    pass
            await self._auto_reconnect()

    async def _handle_quote(self, data: dict) -> None:
        symbol = data.get("S", "")
        quote = Quote(
            symbol=Symbol(ticker=symbol),
            bid=Decimal(str(data.get("bp", 0))) if data.get("bp") else None,
            ask=Decimal(str(data.get("ap", 0))) if data.get("ap") else None,
            volume=data.get("s", 0),
        )
        for cb in self._callbacks:
            try:
                await cb(symbol, quote)
            except Exception as e:
                logger.warning("AlpacaStream callback error: %s", e)

    async def _auto_reconnect(self) -> None:
        for delay in _BACKOFF:
            try:
                logger.info("AlpacaStream reconnecting in %ds", delay)
                await asyncio.sleep(delay)
                await self.reconnect()
                return
            except Exception as e:
                logger.warning("AlpacaStream reconnect failed: %s", e)
        logger.error("AlpacaStream gave up reconnecting")
