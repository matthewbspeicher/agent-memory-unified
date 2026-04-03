import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from adapters.ibkr.connection import IBKRConnection
from broker.errors import BrokerConnectionError


class TestIBKRConnection:
    def setup_method(self):
        self.mock_ib = MagicMock()
        self.mock_ib.connectAsync = AsyncMock()
        self.mock_ib.disconnect = MagicMock()
        self.mock_ib.isConnected = MagicMock(return_value=False)
        self.mock_ib.disconnectedEvent = MagicMock()

    @pytest.mark.asyncio
    async def test_connect_success(self):
        self.mock_ib.isConnected.return_value = True
        conn = IBKRConnection(self.mock_ib, host="127.0.0.1", port=4001, client_id=1)
        await conn.connect()
        self.mock_ib.connectAsync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        conn = IBKRConnection(self.mock_ib, host="127.0.0.1", port=4001, client_id=1)
        await conn.disconnect()
        self.mock_ib.disconnect.assert_called_once()

    def test_is_connected(self):
        self.mock_ib.isConnected.return_value = True
        conn = IBKRConnection(self.mock_ib, host="127.0.0.1", port=4001, client_id=1)
        assert conn.is_connected() is True

    def test_on_disconnected_callback(self):
        conn = IBKRConnection(self.mock_ib, host="127.0.0.1", port=4001, client_id=1)
        callback = MagicMock()
        conn.on_disconnected(callback)
        assert callback in conn._disconnect_callbacks
