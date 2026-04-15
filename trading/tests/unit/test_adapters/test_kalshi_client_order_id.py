import pytest
from unittest.mock import AsyncMock

from trading.adapters.kalshi.client import KalshiClient


@pytest.fixture
def client():
    return KalshiClient(key_id="test", demo=True)


@pytest.mark.asyncio
async def test_create_order_includes_client_order_id_when_provided(client):
    client._post = AsyncMock(return_value={"order": {"order_id": "k_123"}})

    await client.create_order(
        ticker="KXPRES-2024-DJT",
        side="yes",
        count=10,
        price=55,
        client_order_id="01HXX0K9TQVS5N7E2QF7P9V8XQ",
    )

    body = client._post.call_args.args[1]
    assert body["client_order_id"] == "01HXX0K9TQVS5N7E2QF7P9V8XQ"


@pytest.mark.asyncio
async def test_create_order_omits_client_order_id_when_absent(client):
    client._post = AsyncMock(return_value={"order": {"order_id": "k_456"}})

    await client.create_order(ticker="KXTEST", side="yes", count=1, price=50)

    body = client._post.call_args.args[1]
    assert "client_order_id" not in body
