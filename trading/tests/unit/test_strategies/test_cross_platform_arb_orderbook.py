"""Verifies CrossPlatformArbAgent orderbook fallback and native_market_id usage."""

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


def _make_config():
    return AgentConfig(
        name="cross_platform_arb",
        strategy="cross_platform_arb",
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        parameters={"threshold_cents": 8, "min_match_similarity": 0.30},
    )


def _make_agent(kalshi_ds, polymarket_ds):
    return CrossPlatformArbAgent(
        _make_config(),
        kalshi_ds=kalshi_ds,
        polymarket_ds=polymarket_ds,
        spread_store=None,
    )


@pytest.mark.asyncio
async def test_scan_fetches_orderbook_when_nested_prices_are_null(monkeypatch):
    k_market = MagicMock(
        ticker="KTICK",
        native_market_id="KTICK",
        yes_bid=None,
        yes_ask=None,
        title="US trade deficit for 2026",
        volume_usd_24h=Decimal("500"),
    )
    p_market = MagicMock(
        ticker="PTICK",
        native_market_id="PTICK",
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

    candidate = MagicMock(kalshi_ticker="KTICK", poly_ticker="PTICK", final_score=1.0)
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

    agent = _make_agent(kalshi_ds, polymarket_ds)
    opps = await agent.scan(data=MagicMock())

    assert kalshi_ds.get_quote.called, "expected live Kalshi orderbook fetch"
    assert polymarket_ds.get_quote.called, "expected live Polymarket orderbook fetch"
    assert len(opps) == 1
    assert opps[0].data["gap_cents"] == 13


@pytest.mark.asyncio
async def test_scan_uses_native_market_id_for_orderbook_lookup(monkeypatch):
    k_market = MagicMock(
        ticker="KTICK",
        native_market_id="KTICK-MKT1",
        yes_bid=None,
        yes_ask=None,
        title="US trade deficit for 2026",
        volume_usd_24h=Decimal("500"),
    )
    p_market = MagicMock(
        ticker="PTICK",
        native_market_id="0xabc123",
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

    candidate = MagicMock(kalshi_ticker="KTICK", poly_ticker="PTICK", final_score=1.0)
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

    agent = _make_agent(kalshi_ds, polymarket_ds)
    opps = await agent.scan(data=MagicMock())

    kalshi_call_args = kalshi_ds.get_quote.call_args
    assert kalshi_call_args[0][0].ticker == "KTICK-MKT1", (
        "Kalshi orderbook lookup should use native_market_id"
    )
    poly_call_args = polymarket_ds.get_quote.call_args
    assert poly_call_args[0][0].ticker == "0xabc123", (
        "Polymarket orderbook lookup should use native_market_id"
    )
    assert len(opps) == 1


@pytest.mark.asyncio
async def test_scan_skips_pair_when_orderbook_returns_none(monkeypatch):
    k_market = MagicMock(
        ticker="KTICK",
        native_market_id="KTICK",
        yes_bid=None,
        yes_ask=None,
        title="US trade deficit for 2026",
        volume_usd_24h=Decimal("500"),
    )
    p_market = MagicMock(
        ticker="PTICK",
        native_market_id="PTICK",
        yes_bid=None,
        yes_ask=None,
        title="US Trade Deficit in 2026",
        volume_usd_24h=Decimal("500"),
    )

    kalshi_ds = AsyncMock()
    kalshi_ds.get_markets.return_value = [k_market]
    kalshi_ds.get_events.return_value = [k_market]
    kalshi_ds.get_quote.return_value = None

    polymarket_ds = AsyncMock()
    polymarket_ds.get_markets.return_value = [p_market]
    polymarket_ds.get_events.return_value = [p_market]
    polymarket_ds.get_quote.return_value = None

    candidate = MagicMock(kalshi_ticker="KTICK", poly_ticker="PTICK", final_score=1.0)
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

    agent = _make_agent(kalshi_ds, polymarket_ds)
    opps = await agent.scan(data=MagicMock())

    assert len(opps) == 0, "pair with no prices after orderbook fetch should be skipped"


@pytest.mark.asyncio
async def test_scan_uses_cached_prices_when_available(monkeypatch):
    k_market = MagicMock(
        ticker="KTICK",
        native_market_id="KTICK",
        yes_bid=50,
        yes_ask=55,
        title="US trade deficit for 2026",
        volume_usd_24h=Decimal("500"),
    )
    p_market = MagicMock(
        ticker="PTICK",
        native_market_id="PTICK",
        yes_bid=70,
        yes_ask=75,
        title="US Trade Deficit in 2026",
        volume_usd_24h=Decimal("500"),
    )

    kalshi_ds = AsyncMock()
    kalshi_ds.get_markets.return_value = [k_market]
    kalshi_ds.get_events.return_value = [k_market]

    polymarket_ds = AsyncMock()
    polymarket_ds.get_markets.return_value = [p_market]
    polymarket_ds.get_events.return_value = [p_market]

    candidate = MagicMock(kalshi_ticker="KTICK", poly_ticker="PTICK", final_score=1.0)
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

    agent = _make_agent(kalshi_ds, polymarket_ds)
    opps = await agent.scan(data=MagicMock())

    assert not kalshi_ds.get_quote.called, (
        "should not fetch orderbook when cached prices exist"
    )
    assert not polymarket_ds.get_quote.called, (
        "should not fetch orderbook when cached prices exist"
    )
    assert len(opps) == 1
    assert opps[0].data["gap_cents"] == 15
