from __future__ import annotations
import logging
from collections.abc import Callable
from typing import Any

from broker.interfaces import BrokerConnection
from adapters.tradier.client import TradierClient

logger = logging.getLogger(__name__)


class TradierConnection(BrokerConnection):

    def __init__(self, client: TradierClient) -> None:
        self._client = client
        self._connected = False
        self._disconnect_callbacks: list[Callable[[], Any]] = []

    async def connect(self) -> None:
        await self._client.open()
        try:
            await self._client.get_profile()
            self._connected = True
            logger.info("Tradier connected (account=%s)", self._client.account_id)
        except Exception as e:
            self._connected = False
            await self._client.close()
            raise ConnectionError(f"Tradier authentication failed: {e}") from e

    async def disconnect(self) -> None:
        self._connected = False
        await self._client.close()
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception:
                pass

    def is_connected(self) -> bool:
        return self._connected

    def mark_disconnected(self) -> None:
        self._connected = False

    def on_disconnected(self, callback: Callable[[], Any]) -> None:
        self._disconnect_callbacks.append(callback)

    async def reconnect(self) -> None:
        await self.disconnect()
        await self.connect()
