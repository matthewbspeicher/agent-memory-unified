import pytest
from unittest.mock import MagicMock

from adapters.polymarket.client import PolymarketClient
from adapters.polymarket.data_source import PolymarketDataSource


@pytest.fixture
def mock_client():
    c = MagicMock(spec=PolymarketClient)
    return c


@pytest.fixture
def poly_ds(mock_client):
    return PolymarketDataSource(mock_client)


def test_prediction_contract_mapping(poly_ds, mock_client):
    mock_mkt = {
        "condition_id": "0xABC",
        "question": "Will rates hit 5%?",
        "tags": ["Economics", "US"],
        "end_date_iso": "2026-12-31T00:00:00Z",
        "volume_24hr": "1500",
        "closed": False,
        "active": True,
        "tokens": [
            {"outcome": "Yes", "token_id": "0xYES", "price": 0.65},
            {"outcome": "No", "token_id": "0xNO", "price": 0.35},
        ],
    }
    mock_client.get_market.return_value = mock_mkt

    c = poly_ds.get_market("0xABC")
    assert c is not None
    assert c.ticker == "0xABC"
    assert c.title == "Will rates hit 5%?"
    assert c.category == "Economics"

    # 0.65 price -> 65 cents
    assert c.yes_bid == 65
    assert c.volume_24h == 1500
    assert c.result is None

    # Verify cache got populated
    assert poly_ds._token_id_cache["0xABC"] == ("0xYES", "0xNO")


def test_resolve_token_id_cache_hit(poly_ds, mock_client):
    poly_ds._token_id_cache["0xABC"] = ("0xYES", "0xNO")
    token = poly_ds.resolve_token_id("0xABC", "NO")
    assert token == "0xNO"
    assert not mock_client.get_market.called


def test_get_market_by_slug(poly_ds, mock_client):
    mock_client.get_market_by_slug.return_value = {
        "condition_id": "0xABC",
        "tokens": [
            {"outcome": "YES", "token_id": "x"},
            {"outcome": "NO", "token_id": "y"},
        ],
    }
    c = poly_ds.get_market_by_slug("rates-5-percent")
    assert c is not None
    assert mock_client.get_market_by_slug.called
