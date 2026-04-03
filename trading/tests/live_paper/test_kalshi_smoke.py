"""
Kalshi demo API smoke tests.

Marked @pytest.mark.live_paper — not run in normal CI.
Requires: STA_KALSHI_KEY_ID, STA_KALSHI_PRIVATE_KEY_PATH, STA_KALSHI_DEMO=true
"""
from __future__ import annotations

import os

import pytest

from tests.live_paper.conftest import skip_no_kalshi

pytestmark = [
    pytest.mark.live_paper,
]


@pytest.mark.timeout(30)
async def test_public_markets_no_auth(kalshi_client):
    """GET /markets returns open contracts without credentials."""
    page = await kalshi_client.get_markets(status="open", limit=5)
    assert "markets" in page
    assert isinstance(page["markets"], list)
    if page["markets"]:
        m = page["markets"][0]
        assert "ticker" in m
        assert "title" in m


@skip_no_kalshi
@pytest.mark.timeout(30)
async def test_rsa_auth_balance(kalshi_client):
    """RSA signing headers accepted; GET /portfolio/balance returns expected shape."""
    balance = await kalshi_client.get_balance()
    assert isinstance(balance, dict)
    # Kalshi demo balance has at least one of these keys
    assert "available_balance" in balance or "portfolio_value" in balance or "balance" in balance


@pytest.mark.timeout(30)
async def test_get_orderbook(kalshi_client):
    """Fetches orderbook for the first open market; verifies yes/no keys present."""
    page = await kalshi_client.get_markets(status="open", limit=1)
    markets = page.get("markets", [])
    if not markets:
        pytest.skip("No open markets returned by Kalshi demo")
    ticker = markets[0]["ticker"]
    ob = await kalshi_client.get_orderbook(ticker, depth=5)
    assert isinstance(ob, dict)
    # orderbook may have yes/no keys or orderbook_fp with yes_dollars/no_dollars
    fp = ob.get("orderbook_fp", {})
    assert "yes" in ob or "no" in ob or "yes_dollars" in fp or "no_dollars" in fp


@pytest.mark.timeout(30)
async def test_get_quote_via_data_source(kalshi_client):
    """KalshiDataSource.get_quote() returns a Quote with non-None bid or ask."""
    from adapters.kalshi.data_source import KalshiDataSource
    from broker.models import AssetType, Symbol
    ds = KalshiDataSource(kalshi_client)
    page = await kalshi_client.get_markets(status="open", limit=10)
    markets = page.get("markets", [])
    if not markets:
        pytest.skip("No open markets returned by Kalshi demo")
    for market in markets:
        sym = Symbol(ticker=market["ticker"], asset_type=AssetType.PREDICTION)
        quote = await ds.get_quote(sym)
        if quote is not None and (quote.bid is not None or quote.ask is not None):
            return  # passed
    pytest.skip("No open markets had bids/asks to form a quote")


@skip_no_kalshi
@pytest.mark.timeout(30)
async def test_get_positions_authenticated(kalshi_client):
    """GET /portfolio/positions returns a list (may be empty)."""
    positions = await kalshi_client.get_positions()
    assert isinstance(positions, list)


@skip_no_kalshi
@pytest.mark.timeout(30)
async def test_get_order_history_authenticated(kalshi_client):
    """GET /portfolio/orders returns a list (may be empty)."""
    orders = await kalshi_client.get_order_history(limit=10)
    assert isinstance(orders, list)


@pytest.mark.timeout(30)
async def test_place_and_cancel_paper_order(kalshi_paper_broker, kalshi_client):
    """
    Creates a LimitOrder -> KalshiPaperBroker.place_order() -> OrderStatus.FILLED.
    No real order is submitted to Kalshi.
    """
    from adapters.kalshi.paper import KALSHI_PAPER_ACCOUNT_ID
    from broker.models import AssetType, LimitOrder, OrderSide, Symbol, TIF
    from decimal import Decimal

    page = await kalshi_client.get_markets(status="open", limit=1)
    markets = page.get("markets", [])
    if not markets:
        pytest.skip("No open markets returned by Kalshi demo")

    ticker = markets[0]["ticker"]
    sym = Symbol(ticker=ticker, asset_type=AssetType.PREDICTION)
    order = LimitOrder(
        symbol=sym,
        side=OrderSide.BUY,
        quantity=Decimal("5"),
        limit_price=Decimal("0.40"),
        account_id=KALSHI_PAPER_ACCOUNT_ID,
        time_in_force=TIF.GTC,
    )
    from broker.models import OrderStatus
    result = await kalshi_paper_broker.orders.place_order(KALSHI_PAPER_ACCOUNT_ID, order)
    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == Decimal("5")
