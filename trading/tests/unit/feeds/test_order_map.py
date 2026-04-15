import pytest
from unittest.mock import AsyncMock, MagicMock

from trading.feeds.order_map import OrderMap


def _make_mock_pool(conn):
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.mark.asyncio
async def test_record_inserts_mapping():
    conn = AsyncMock()
    pool = _make_mock_pool(conn)
    om = OrderMap(pool)
    await om.record(order_hash="0xabc", signal_id="01HXXSIG", venue="polymarket")
    conn.execute.assert_called_once()
    args = conn.execute.call_args
    assert args[0][1] == "0xabc"
    assert args[0][2] == "01HXXSIG"
    assert args[0][3] == "polymarket"
    assert "ON CONFLICT (order_hash) DO NOTHING" in args[0][0]


@pytest.mark.asyncio
async def test_lookup_returns_signal_id():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"signal_id": "01HXXSIG"}
    pool = _make_mock_pool(conn)
    om = OrderMap(pool)
    result = await om.lookup("0xabc")
    assert result == "01HXXSIG"


@pytest.mark.asyncio
async def test_lookup_missing_returns_none():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = _make_mock_pool(conn)
    om = OrderMap(pool)
    assert await om.lookup("0xnonexistent") is None
