from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest


async def test_connect_success():
    from adapters.alpaca.connection import AlpacaConnection

    mock_client = MagicMock()
    mock_client.open = AsyncMock()
    mock_client.get_account = AsyncMock(return_value={"id": "acc1", "status": "ACTIVE"})

    conn = AlpacaConnection(mock_client)
    await conn.connect()

    assert conn.is_connected() is True
    mock_client.open.assert_called_once()
    mock_client.get_account.assert_called_once()


async def test_connect_failure():
    from adapters.alpaca.connection import AlpacaConnection

    mock_client = MagicMock()
    mock_client.open = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.get_account = AsyncMock(side_effect=Exception("auth failed"))

    conn = AlpacaConnection(mock_client)
    with pytest.raises(ConnectionError):
        await conn.connect()

    assert conn.is_connected() is False


async def test_disconnect():
    from adapters.alpaca.connection import AlpacaConnection

    mock_client = MagicMock()
    mock_client.open = AsyncMock()
    mock_client.get_account = AsyncMock(return_value={"id": "acc1"})
    mock_client.close = AsyncMock()

    conn = AlpacaConnection(mock_client)
    await conn.connect()
    await conn.disconnect()

    assert conn.is_connected() is False
    mock_client.close.assert_called_once()


async def test_reconnect():
    from adapters.alpaca.connection import AlpacaConnection

    mock_client = MagicMock()
    mock_client.open = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.get_account = AsyncMock(return_value={"id": "acc1"})

    conn = AlpacaConnection(mock_client)
    await conn.connect()
    await conn.reconnect()

    assert conn.is_connected() is True
    assert mock_client.close.call_count == 1
    assert mock_client.open.call_count == 2
