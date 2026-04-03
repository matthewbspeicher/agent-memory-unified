from __future__ import annotations
import logging
from collections.abc import Callable
from typing import Any

from broker.interfaces import BrokerConnection
from adapters.alpaca.client import AlpacaClient

logger = logging.getLogger(__name__)


class AlpacaConnection(BrokerConnection):
    """REST health-check based connection for Alpaca."""

    def __init__(self, client: AlpacaClient) -> None:
        self._client = client
        self._connected = False
        self._disconnect_callbacks: list[Callable[[], Any]] = []
        self._account_id: str | None = None

    async def connect(self) -> None:
        await self._client.open()
        try:
            account = await self._client.get_account()
            self._account_id = account.get("id")
            self._connected = True
            logger.info("Alpaca connected (account=%s)", self._account_id)
        except Exception as e:
            self._connected = False
            await self._client.close()
            raise ConnectionError(f"Alpaca authentication failed: {e}") from e

    async def disconnect(self) -> None:
        self._connected = False
        await self._client.close()
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception:
                pass
        logger.info("Alpaca disconnected")

    def is_connected(self) -> bool:
        return self._connected

    def mark_disconnected(self) -> None:
        """Called by other components when an API call fails with auth error."""
        self._connected = False

    def on_disconnected(self, callback: Callable[[], Any]) -> None:
        self._disconnect_callbacks.append(callback)

    async def reconnect(self) -> None:
        await self.disconnect()
        await self.connect()

    @property
    def account_id(self) -> str | None:
        return self._account_id
