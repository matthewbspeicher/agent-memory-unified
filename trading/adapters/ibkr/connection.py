from __future__ import annotations
import asyncio
import logging
from collections.abc import Callable
from typing import Any

from ib_async import IB

from broker.errors import BrokerConnectionError
from broker.interfaces import BrokerConnection

logger = logging.getLogger(__name__)


class IBKRConnection(BrokerConnection):
    def __init__(
        self,
        ib: IB,
        host: str = "127.0.0.1",
        port: int = 4001,
        client_id: int = 1,
        initial_delay: int = 5,
        max_delay: int = 60,
    ):
        self._ib = ib
        self._host = host
        self._port = port
        self._client_id = client_id
        self._initial_delay = initial_delay
        self._max_delay = max_delay
        self._disconnect_callbacks: list[Callable[[], Any]] = []
        self._reconnecting = False

        self._ib.disconnectedEvent += self._on_disconnect

    async def connect(self) -> None:
        try:
            await self._ib.connectAsync(
                self._host,
                self._port,
                clientId=self._client_id,
            )
            logger.info("Connected to IBKR at %s:%s", self._host, self._port)
        except Exception as e:
            raise BrokerConnectionError(f"Failed to connect: {e}") from e

    async def disconnect(self) -> None:
        self._ib.disconnect()
        logger.info("Disconnected from IBKR")

    def is_connected(self) -> bool:
        return self._ib.isConnected()

    def on_disconnected(self, callback: Callable[[], Any]) -> None:
        self._disconnect_callbacks.append(callback)

    async def reconnect(self) -> None:
        delay = self._initial_delay
        while not self.is_connected():
            try:
                logger.info("Reconnecting in %ds...", delay)
                await asyncio.sleep(delay)
                await self.connect()
                logger.info("Reconnected successfully")
                return
            except BrokerConnectionError:
                delay = min(delay * 2, self._max_delay)

    def _on_disconnect(self) -> None:
        logger.warning("IBKR connection lost")
        for callback in self._disconnect_callbacks:
            try:
                callback()
            except Exception:
                logger.exception("Error in disconnect callback")

        if not self._reconnecting:
            self._reconnecting = True
            asyncio.ensure_future(self._auto_reconnect())

    async def _auto_reconnect(self) -> None:
        try:
            await self.reconnect()
        finally:
            self._reconnecting = False
