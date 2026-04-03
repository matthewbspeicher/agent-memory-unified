from decimal import Decimal
from unittest.mock import AsyncMock
from broker.models import Quote, Symbol, ContractDetails

HEADERS = {"X-API-Key": "test-key"}


def test_get_quote(client, mock_broker):
    mock_broker.market_data.get_quote = AsyncMock(return_value=Quote(
        symbol=Symbol(ticker="AAPL"), bid=Decimal("150.00"),
        ask=Decimal("150.05"), last=Decimal("150.02"), volume=1000000,
    ))
    resp = client.get("/quotes/AAPL", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"]["ticker"] == "AAPL"
    assert data["bid"] == "150.00"


def test_get_batch_quotes(client, mock_broker):
    mock_broker.market_data.get_quotes = AsyncMock(return_value=[
        Quote(symbol=Symbol(ticker="AAPL"), last=Decimal("150")),
        Quote(symbol=Symbol(ticker="MSFT"), last=Decimal("400")),
    ])
    resp = client.get("/quotes?symbols=AAPL,MSFT", headers=HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_contract_details(client, mock_broker):
    mock_broker.market_data.get_contract_details = AsyncMock(return_value=ContractDetails(
        symbol=Symbol(ticker="AAPL"), long_name="Apple Inc.",
        industry="Technology", category="Computers",
    ))
    resp = client.get("/contracts/AAPL", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["long_name"] == "Apple Inc."
