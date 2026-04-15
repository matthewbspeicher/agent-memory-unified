"""Integration tests for Kalshi orderbook fetch via KalshiDataSource.get_quote.

Skipped automatically unless KALSHI_INTEGRATION=true is set.
Requires STA_KALSHI_KEY_ID + STA_KALSHI_PRIVATE_KEY_PATH env vars.

Run with:
  KALSHI_INTEGRATION=true pytest tests/integration/test_kalshi_orderbook.py -v

Mirrors test_polymarket_orderbook.py — verifies the same two properties
on the Kalshi side:
 1) get_quote hits /markets/{ticker}/orderbook successfully and returns a
    Quote with at least bid or ask populated.
 2) native_market_id is populated on live markets (equal to Kalshi's
    market ticker, since _parse_market sets native_market_id=m["ticker"]).
"""

from __future__ import annotations

import os

import pytest

INTEGRATION_ENABLED = os.getenv("KALSHI_INTEGRATION", "").lower() == "true"

skip_unless_integration = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="KALSHI_INTEGRATION=true required",
)


def _build_data_source():
    """Construct a live KalshiDataSource using the same factory path
    as trading/api/startup/integrations.py::setup_kalshi."""
    from config import load_config
    from adapters.kalshi.client import KalshiClient
    from adapters.kalshi.data_source import KalshiDataSource

    cfg = load_config()
    if not cfg.kalshi_key_id or not cfg.kalshi_private_key_path:
        pytest.skip("STA_KALSHI_KEY_ID / STA_KALSHI_PRIVATE_KEY_PATH not set")

    client = KalshiClient(
        key_id=cfg.kalshi_key_id,
        private_key_path=cfg.kalshi_private_key_path,
        demo=cfg.kalshi_demo,
    )
    return KalshiDataSource(client)


@skip_unless_integration
@pytest.mark.asyncio
async def test_get_quote_returns_live_orderbook():
    """get_quote hits the live Kalshi orderbook and returns Quote.bid or Quote.ask.

    Uses the /events endpoint to pick a representative first-nested-market
    ticker — matches production usage in CrossPlatformArbAgent.scan() and
    avoids the sports-prop aggregate tickers that /markets sorts first
    (KXMVESPORTSMULTIGAMEEXTENDED-*, no quotes, not tradeable).
    """
    from broker.models import AssetType, Symbol

    ds = _build_data_source()
    events = await ds.get_events(max_pages=1)
    assert len(events) > 0, "expected at least one Kalshi event"

    # Try up to 10 events; pass as soon as one returns live bid or ask.
    # Some events may be resolved / paused / thin — tolerate that, don't
    # require every ticker to have a quote.
    last_err = None
    for ev in events[:10]:
        ticker = ev.native_market_id or ev.ticker
        quote = await ds.get_quote(
            Symbol(ticker=ticker, asset_type=AssetType.PREDICTION)
        )
        if quote is not None and (quote.bid is not None or quote.ask is not None):
            return  # PASS
        last_err = f"{ticker}: quote={quote}"
    pytest.fail(
        f"no live bid/ask on any of the first 10 Kalshi event markets; "
        f"last probed: {last_err}"
    )


@skip_unless_integration
@pytest.mark.asyncio
async def test_native_market_id_populated_in_market_data():
    """Kalshi markets should have native_market_id set (equals market ticker)."""
    ds = _build_data_source()
    markets = await ds.get_markets(max_pages=1)
    assert len(markets) > 0

    for mkt in markets:
        assert mkt.native_market_id is not None, (
            f"market {mkt.ticker} should have native_market_id"
        )
        # On Kalshi, the market ticker IS the native identifier.
        assert mkt.native_market_id == mkt.ticker, (
            f"expected native_market_id==ticker for Kalshi market {mkt.ticker}, "
            f"got native_market_id={mkt.native_market_id}"
        )


@skip_unless_integration
@pytest.mark.asyncio
async def test_native_market_id_populated_in_event_data():
    """Kalshi events should have native_market_id set to the first nested market's ticker."""
    ds = _build_data_source()
    events = await ds.get_events(max_pages=1)
    assert len(events) > 0, "expected at least one Kalshi event"

    for ev in events:
        assert ev.native_market_id is not None, (
            f"event contract {ev.ticker} should have native_market_id"
        )
