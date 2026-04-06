from unittest.mock import AsyncMock
from broker.models import OrderResult, OrderStatus

HEADERS = {"X-API-Key": "test-key"}


def test_place_market_order(client, mock_broker):
    mock_broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="12345",
            status=OrderStatus.SUBMITTED,
        )
    )
    resp = client.post(
        "/orders",
        headers=HEADERS,
        json={
            "symbol": {"ticker": "AAPL"},
            "side": "BUY",
            "quantity": "100",
            "account_id": "U12345",
            "order_type": "market",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["order_id"] == "12345"


def test_place_limit_order(client, mock_broker):
    mock_broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="12346",
            status=OrderStatus.SUBMITTED,
        )
    )
    resp = client.post(
        "/orders",
        headers=HEADERS,
        json={
            "symbol": {"ticker": "AAPL"},
            "side": "BUY",
            "quantity": "50",
            "account_id": "U12345",
            "order_type": "limit",
            "limit_price": "150.00",
        },
    )
    assert resp.status_code == 200


def test_cancel_order(client, mock_broker):
    mock_broker.orders.cancel_order = AsyncMock(
        return_value=OrderResult(
            order_id="12345",
            status=OrderStatus.CANCELLED,
        )
    )
    resp = client.delete("/orders/12345", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_get_order_status(client, mock_broker):
    mock_broker.orders.get_order_status = AsyncMock(return_value=OrderStatus.FILLED)
    resp = client.get("/orders/12345", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "FILLED"
