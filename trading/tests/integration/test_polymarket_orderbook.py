"""Integration tests for Polymarket orderbook fallback.

Skipped automatically unless POLYMARKET_INTEGRATION=true is set.
Run with: POLYMARKET_INTEGRATION=true pytest tests/integration/test_polymarket_orderbook.py -v
"""

from __future__ import annotations

import os

import pytest

INTEGRATION_ENABLED = os.getenv("POLYMARKET_INTEGRATION", "").lower() == "true"

skip_unless_integration = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="POLYMARKET_INTEGRATION=true required",
)


def _build_data_source():
    """Construct a live PolymarketDataSource using the same factory path
    as trading/api/startup/integrations.py::setup_polymarket."""
    from config import load_config
    from adapters.polymarket.client import PolymarketClient
    from adapters.polymarket.data_source import PolymarketDataSource

    cfg = load_config()
    client = PolymarketClient(
        private_key=cfg.polymarket_private_key,
        funder=cfg.polymarket_funder or "",
        api_key=cfg.polymarket_api_key,
        signature_type=cfg.polymarket_signature_type,
        creds_path=cfg.polymarket_creds_path,
        rpc_url=cfg.polymarket_rpc_url,
        dry_run=cfg.polymarket_dry_run,
        relayer_api_key=cfg.polymarket_relayer_api_key,
        relayer_address=cfg.polymarket_relayer_address,
    )
    return PolymarketDataSource(client)


@skip_unless_integration
@pytest.mark.asyncio
async def test_get_quote_returns_live_orderbook_for_null_prices():
    """When cached bid/ask are None, get_quote falls back to CLOB orderbook."""
    from broker.models import AssetType, Symbol

    ds = _build_data_source()
    markets = await ds.get_markets(limit=5)
    assert len(markets) > 0, "expected at least one Polymarket market"

    market = markets[0]
    quote = await ds.get_quote(
        Symbol(ticker=market.ticker, asset_type=AssetType.PREDICTION)
    )
    assert quote is not None, "expected a quote for the market"
    assert quote.bid is not None or quote.ask is not None, (
        "expected at least bid or ask from orderbook fallback"
    )


@skip_unless_integration
@pytest.mark.asyncio
async def test_native_market_id_populated_in_market_data():
    """Polymarket markets should have native_market_id set to conditionId."""
    ds = _build_data_source()
    markets = await ds.get_markets(limit=5)
    assert len(markets) > 0

    for mkt in markets:
        assert mkt.native_market_id is not None, (
            f"market {mkt.ticker} should have native_market_id (conditionId)"
        )
