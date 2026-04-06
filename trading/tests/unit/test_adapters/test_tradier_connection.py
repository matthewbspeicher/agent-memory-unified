from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest


async def test_connect_success():
    from adapters.tradier.connection import TradierConnection

    mock_client = MagicMock()
    mock_client.open = AsyncMock()
    mock_client.get_profile = AsyncMock(
        return_value={
            "profile": {"account": {"account_number": "acc1"}},
        }
    )

    conn = TradierConnection(mock_client)
    await conn.connect()
    assert conn.is_connected() is True


async def test_connect_failure():
    from adapters.tradier.connection import TradierConnection

    mock_client = MagicMock()
    mock_client.open = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.get_profile = AsyncMock(side_effect=Exception("auth failed"))

    conn = TradierConnection(mock_client)
    with pytest.raises(ConnectionError):
        await conn.connect()
    assert conn.is_connected() is False


async def test_disconnect():
    from adapters.tradier.connection import TradierConnection

    mock_client = MagicMock()
    mock_client.open = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.get_profile = AsyncMock(return_value={"profile": {"account": {}}})

    conn = TradierConnection(mock_client)
    await conn.connect()
    await conn.disconnect()
    assert conn.is_connected() is False
