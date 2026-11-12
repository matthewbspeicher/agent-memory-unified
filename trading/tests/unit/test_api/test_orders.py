from datetime import datetime, timezone
from decimal import Decimal
import pytest
from execution.context import AccountRiskState
from broker.models import AccountBalance, Quote
from risk.rules import PortfolioContext
from unittest.mock import AsyncMock
from broker.models import OrderResult, OrderStatus


@pytest.fixture(autouse=True)
def measured_account(mock_broker):
    async def state(account):
        return AccountRiskState(
            PortfolioContext(
                [],
                AccountBalance(
                    account, Decimal(100000), Decimal(50000), Decimal(50000), Decimal(0)
                ),
                daily_pnl=Decimal(0),
                daily_trade_count=0,
            ),
            datetime.now(timezone.utc),
            [],
            "mock-ledger",
        )

    mock_broker.account.get_risk_state = AsyncMock(side_effect=state)
    mock_broker.market_data.get_quote = AsyncMock(
        side_effect=lambda symbol: Quote(symbol, last=Decimal(50))
    )


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


def test_risk_rejection_and_missing_provider_never_submit(client, mock_broker):
    from execution.context import AccountRiskState

    payload = {
        "symbol": {"ticker": "AAPL"},
        "side": "BUY",
        "quantity": "600",
        "account_id": "U12345",
        "order_type": "market",
    }
    mock_broker.orders.place_order = AsyncMock()
    response = client.post("/orders", headers=HEADERS, json=payload)
    assert response.status_code == 409
    mock_broker.orders.place_order.assert_not_awaited()
    mock_broker.account.get_risk_state.side_effect = NotImplementedError("unsupported")
    payload["quantity"] = "1"
    assert client.post("/orders", headers=HEADERS, json=payload).status_code == 503
    mock_broker.orders.place_order.assert_not_awaited()


def test_amendment_api_uses_full_known_order_and_allowlist(client, mock_broker):
    from broker.models import MarketOrder, OrderSide, Symbol
    from execution.context import OrderSnapshot

    mock_broker.orders.place_order = AsyncMock(
        return_value=OrderResult("known", OrderStatus.SUBMITTED)
    )
    mock_broker.orders.modify_order = AsyncMock(
        return_value=OrderResult("known", OrderStatus.SUBMITTED)
    )
    payload = {
        "symbol": {"ticker": "AAPL"},
        "side": "BUY",
        "quantity": "10",
        "account_id": "U12345",
        "order_type": "market",
    }
    assert client.post("/orders", headers=HEADERS, json=payload).status_code == 200

    async def state(account):
        return AccountRiskState(
            PortfolioContext(
                [],
                AccountBalance(
                    account, Decimal(100000), Decimal(50000), Decimal(50000), Decimal(0)
                ),
                daily_pnl=Decimal(0),
                daily_trade_count=1,
            ),
            datetime.now(timezone.utc),
            [
                OrderSnapshot(
                    "known",
                    MarketOrder(Symbol("AAPL"), OrderSide.BUY, Decimal(10), account),
                    OrderStatus.SUBMITTED,
                )
            ],
            "mock-ledger",
        )

    mock_broker.account.get_risk_state.side_effect = state
    assert (
        client.patch(
            "/orders/known", headers=HEADERS, json={"totalQuantity": 1000}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            "/orders/missing", headers=HEADERS, json={"quantity": 1}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            "/orders/known", headers=HEADERS, json={"quantity": 600}
        ).status_code
        == 409
    )
    mock_broker.orders.modify_order.assert_not_awaited()
    assert (
        client.patch(
            "/orders/known", headers=HEADERS, json={"quantity": 15}
        ).status_code
        == 200
    )
    mock_broker.orders.modify_order.assert_awaited_once_with(
        "known", {"quantity": Decimal(15)}
    )
