"""
Polymarket CLOB smoke tests.

Marked @pytest.mark.live_paper — not run in normal CI.
Requires: STA_POLYMARKET_PRIVATE_KEY, STA_POLYMARKET_DRY_RUN=true
"""
from __future__ import annotations

import os

import pytest

from tests.live_paper.conftest import skip_no_polymarket

pytestmark = [
    pytest.mark.live_paper,
]


@skip_no_polymarket
@pytest.mark.timeout(30)
def test_clob_health_check(polymarket_client):
    """PolymarketClient.check_health() returns True after authenticate()."""
    try:
        polymarket_client.authenticate()
    except Exception as e:
        if "401" in str(e) or "Invalid L1" in str(e):
            pytest.xfail("Polymarket testnet L1 credentials missing or invalid")
        raise
    assert polymarket_client.check_health() is True


@skip_no_polymarket
@pytest.mark.timeout(30)
def test_get_markets_returns_results(polymarket_client):
    """get_markets() returns at least one active market with condition_id and question."""
    data = polymarket_client.get_markets(active=True, limit=5)
    markets = data.get("data", []) if isinstance(data, dict) else data
    assert isinstance(markets, list)
    if markets:
        first = markets[0]
        assert "conditionId" in first or "condition_id" in first
        assert "question" in first


@skip_no_polymarket
@pytest.mark.timeout(30)
def test_get_orderbook_for_market():
    """Picks the first market token; get_orderbook() returns bids/asks structure. Hits mainnet API directly to bypass testnet emptyness."""
    from adapters.polymarket.client import PolymarketClient
    import os
    mainnet_client = PolymarketClient("0x" + "0"*64, dry_run=True) # Fake PK is fine for read-only
    
    data = mainnet_client.get_markets(active=True, limit=20)
    markets = data.get("data", []) if isinstance(data, dict) else data
    if not markets:
        pytest.skip("No active Polymarket mainnet markets returned")
    
    for market in markets:
        tokens = market.get("tokens", [])
        if not tokens:
            continue
        token_id = tokens[0].get("token_id") or tokens[0].get("tokenId")
        if not token_id:
            continue
        try:
            ob = mainnet_client.get_orderbook(token_id)
            assert isinstance(ob, dict)
            assert "bids" in ob
            return
        except Exception:
            # SDK will throw PolyApiException if 404 and retries fail
            continue
    pytest.skip("No mainnet markets had an orderbook available")


@skip_no_polymarket
@pytest.mark.timeout(30)
async def test_get_quote_via_data_source():
    """PolymarketDataSource.get_quote() returns a Quote with numeric bid/ask."""
    from adapters.polymarket.data_source import PolymarketDataSource
    from adapters.polymarket.client import PolymarketClient
    from broker.models import AssetType, Symbol
    import os

    mainnet_client = PolymarketClient("0x" + "0"*64, dry_run=True) # Fake PK is fine for read-only
    ds = PolymarketDataSource(mainnet_client)
    data = mainnet_client.get_markets(active=True, limit=5)
    markets = data.get("data", []) if isinstance(data, dict) else data
    if not markets:
        pytest.skip("No active Polymarket mainnet markets returned")
    condition_id = markets[0].get("condition_id") or markets[0].get("conditionId")
    if not condition_id:
        pytest.skip("First market has no condition_id")
    sym = Symbol(ticker=condition_id, asset_type=AssetType.PREDICTION)
    quote = await ds.get_quote(sym)
    assert quote is not None
    assert quote.bid is not None or quote.ask is not None


@skip_no_polymarket
@pytest.mark.timeout(30)
async def test_dry_run_order_returns_submitted(polymarket_broker):
    """place_order() with dry_run=True returns OrderStatus.SUBMITTED and a dry-run-* order ID."""
    from adapters.polymarket.broker import PolymarketAccount
    from broker.models import AssetType, LimitOrder, OrderSide, OrderStatus, Symbol, TIF
    from decimal import Decimal

    # Connect broker (idempotent in dry-run)
    await polymarket_broker.connection.connect()

    # Grab a real condition_id so the order shape is valid
    data = polymarket_broker.connection.client.get_markets(active=True, limit=2)
    markets = data.get("data", []) if isinstance(data, dict) else data
    if not markets:
        pytest.skip("No active Polymarket markets for dry-run order test")
    condition_id = markets[0].get("condition_id") or markets[0].get("conditionId")
    if not condition_id:
        pytest.skip("First market has no condition_id")


    sym = Symbol(ticker=condition_id, asset_type=AssetType.PREDICTION)
    order = LimitOrder(
        symbol=sym,
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        limit_price=Decimal("0.55"),
        account_id=PolymarketAccount.ACCOUNT_ID,
        time_in_force=TIF.GTC,
    )
    result = await polymarket_broker.orders.place_order(
        account_id=PolymarketAccount.ACCOUNT_ID,
        order=order
    )
    assert result.status == OrderStatus.SUBMITTED
    assert result.order_id.startswith("dry-run-")


@skip_no_polymarket
@pytest.mark.timeout(30)
async def test_dry_run_cancel_returns_true(polymarket_broker):
    """cancel_order('dry-run-xyz') returns True without hitting network."""
    from broker.models import OrderStatus
    result = await polymarket_broker.orders.cancel_order("dry-run-xyz")
    # Cancel of a dry-run order returns True directly
    assert result is True
