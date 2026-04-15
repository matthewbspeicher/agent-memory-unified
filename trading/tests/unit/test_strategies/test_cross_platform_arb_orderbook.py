"""Verifies CrossPlatformArbAgent falls back to live orderbook when nested-market prices are null."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.models import ActionLevel, AgentConfig
from strategies.cross_platform_arb import CrossPlatformArbAgent


class _FakeMatcher:
    def __init__(self, pairs):
        self._pairs = pairs

    def __call__(self, k_markets, p_markets, min_score):
        return self._pairs


@pytest.mark.asyncio
async def test_scan_fetches_orderbook_when_nested_prices_are_null(monkeypatch):
    # Kalshi nested market with null prices, orderbook has 55¢/57¢
    k_market = MagicMock(
        ticker="KTICK",
        yes_bid=None,
        yes_ask=None,
        title="US trade deficit for 2026",
        volume_usd_24h=Decimal("500"),
    )
    p_market = MagicMock(
        ticker="PTICK",
        yes_bid=None,
        yes_ask=None,
        title="US Trade Deficit in 2026",
        volume_usd_24h=Decimal("500"),
    )

    kalshi_ds = AsyncMock()
    kalshi_ds.get_markets.return_value = [k_market]
    kalshi_ds.get_events.return_value = [k_market]
    kalshi_ds.get_quote.return_value = MagicMock(
        bid=Decimal("0.55"), ask=Decimal("0.57")
    )

    polymarket_ds = AsyncMock()
    polymarket_ds.get_markets.return_value = [p_market]
    polymarket_ds.get_events.return_value = [p_market]
    polymarket_ds.get_quote.return_value = MagicMock(
        bid=Decimal("0.70"), ask=Decimal("0.72")
    )

    candidate = MagicMock(
        kalshi_ticker="KTICK", poly_ticker="PTICK", final_score=1.0
    )
    monkeypatch.setattr(
        "strategies.cross_platform_arb.match_markets",
        _FakeMatcher([candidate]),
    )
    monkeypatch.setattr(
        "strategies.cross_platform_arb.normalize_contract",
        lambda m, platform: MagicMock(volume_usd_24h=Decimal("500")),
    )
    monkeypatch.setattr(
        "strategies.cross_platform_arb.compute_confidence",
        lambda **_: 0.8,
    )

    config = AgentConfig(
        name="cross_platform_arb",
        strategy="cross_platform_arb",
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        parameters={"threshold_cents": 8, "min_match_similarity": 0.30},
    )
    agent = CrossPlatformArbAgent(
        config, kalshi_ds=kalshi_ds, polymarket_ds=polymarket_ds, spread_store=None
    )

    opps = await agent.scan(data=MagicMock())

    assert kalshi_ds.get_quote.called, "expected live Kalshi orderbook fetch"
    assert polymarket_ds.get_quote.called, "expected live Polymarket orderbook fetch"
    assert len(opps) == 1
    # Kalshi buy leg uses ask=57¢; Polymarket sell leg uses bid=70¢; |57-70|=13.
    # (Task spec said 15, which does not match the buy-ask / sell-bid formula.)
    assert opps[0].data["gap_cents"] == 13
