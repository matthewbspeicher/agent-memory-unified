from decimal import Decimal
from unittest.mock import AsyncMock
from broker.models import Account, AccountBalance, Position, Symbol

HEADERS = {"X-API-Key": "test-key"}


def test_list_accounts(client, mock_broker):
    mock_broker.account.get_accounts = AsyncMock(
        return_value=[Account(account_id="U12345"), Account(account_id="U67890")]
    )
    resp = client.get("/accounts", headers=HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert resp.json()[0]["account_id"] == "U12345"


def test_get_positions(client, mock_broker):
    mock_broker.account.get_positions = AsyncMock(return_value=[
        Position(
            symbol=Symbol(ticker="AAPL"), quantity=Decimal("100"),
            avg_cost=Decimal("150"), market_value=Decimal("15500"),
            unrealized_pnl=Decimal("500"), realized_pnl=Decimal("0"),
        )
    ])
    resp = client.get("/accounts/U12345/positions", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["symbol"]["ticker"] == "AAPL"


def test_get_balances(client, mock_broker):
    mock_broker.account.get_balances = AsyncMock(return_value=AccountBalance(
        account_id="U12345", net_liquidation=Decimal("100000"),
        buying_power=Decimal("200000"), cash=Decimal("50000"),
        maintenance_margin=Decimal("10000"),
    ))
    resp = client.get("/accounts/U12345/balances", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["net_liquidation"] == "100000"
