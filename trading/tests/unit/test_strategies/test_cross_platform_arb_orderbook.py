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


@pytest.mark.asyncio
async def test_scan_skips_pair_when_orderbook_returns_zero_bid(monkeypatch):
    """Dead-book filter: illiquid CLOB markets return bid=0 / ask=None.

    Verified live 2026-04-15: 4/4 null-cached Gamma events filled via
    `_orderbook_fallback` with bid=Decimal("0"), which is not tradable.
    scan() must skip these rather than emit a fake opportunity with
    gap_cents = |k_cents - 0|.
    """
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
    # Dead book: orderbook fallback reached CLOB but found bid=0.
    polymarket_ds.get_quote.return_value = MagicMock(bid=Decimal("0"), ask=None)

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

    assert len(opps) == 0, (
        "scan must skip pairs where orderbook fallback returned bid=0 "
        "(dead CLOB book, not a tradable price)"
    )


# ---------------------------------------------------------------------------
# arb.spread event emission (Phase 1 — wires cron scan into ArbExecutor)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_publishes_arb_spread_event_when_event_bus_wired(monkeypatch):
    """When event_bus is wired and a spread observation is recorded, scan
    publishes an arb.spread event with the observation_id so the
    ArbExecutor can claim and atomically execute the 2-leg trade."""
    k_market = MagicMock(
        ticker="KTICK",
        native_market_id="KTICK",
        yes_bid=55,
        yes_ask=57,
        title="US trade deficit for 2026",
        volume_usd_24h=Decimal("500"),
    )
    p_market = MagicMock(
        ticker="PTICK",
        native_market_id="PTICK",
        yes_bid=70,
        yes_ask=72,
        title="US Trade Deficit in 2026",
        volume_usd_24h=Decimal("500"),
    )

    kalshi_ds = AsyncMock()
    kalshi_ds.get_events.return_value = [k_market]
    polymarket_ds = AsyncMock()
    polymarket_ds.get_events.return_value = [p_market]

    spread_store = AsyncMock()
    spread_store.record = AsyncMock(return_value=12345)  # observation_id

    event_bus = AsyncMock()

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

    agent = CrossPlatformArbAgent(
        _make_config(),
        kalshi_ds=kalshi_ds,
        polymarket_ds=polymarket_ds,
        spread_store=spread_store,
        event_bus=event_bus,
    )
    opps = await agent.scan(data=MagicMock())

    # Opportunity emitted as before
    assert len(opps) == 1
    # And event_bus.publish called once with arb.spread + the observation_id
    assert event_bus.publish.await_count == 1
    topic, payload = event_bus.publish.await_args.args
    assert topic == "arb.spread"
    assert payload["observation_id"] == 12345
    assert payload["kalshi_ticker"] == "KTICK"
    assert payload["poly_ticker"] == "PTICK"
    # Convention: kalshi=ask (57), poly=bid (70), gap=13
    assert payload["kalshi_cents"] == 57
    assert payload["poly_cents"] == 70
    assert payload["gap_cents"] == 13


@pytest.mark.asyncio
async def test_scan_does_not_publish_when_event_bus_is_none(monkeypatch):
    """Regression guard: tests that don't wire event_bus must not blow up
    and must not publish anything."""
    k_market = MagicMock(
        ticker="KTICK",
        native_market_id="KTICK",
        yes_bid=55,
        yes_ask=57,
        title="A",
        volume_usd_24h=Decimal("500"),
    )
    p_market = MagicMock(
        ticker="PTICK",
        native_market_id="PTICK",
        yes_bid=70,
        yes_ask=72,
        title="A",
        volume_usd_24h=Decimal("500"),
    )

    kalshi_ds = AsyncMock()
    kalshi_ds.get_events.return_value = [k_market]
    polymarket_ds = AsyncMock()
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

    # No event_bus, no spread_store — exact shape used by older tests
    agent = _make_agent(kalshi_ds, polymarket_ds)
    opps = await agent.scan(data=MagicMock())

    assert len(opps) == 1  # opportunity still emitted
    # No assertion on publish — just confirm we don't crash.


@pytest.mark.asyncio
async def test_scan_event_bus_failure_is_swallowed(monkeypatch):
    """Defensive: a misbehaving event_bus must not block opportunity
    emission. Publish errors log a warning and continue."""
    k_market = MagicMock(
        ticker="KTICK",
        native_market_id="KTICK",
        yes_bid=55,
        yes_ask=57,
        title="A",
        volume_usd_24h=Decimal("500"),
    )
    p_market = MagicMock(
        ticker="PTICK",
        native_market_id="PTICK",
        yes_bid=70,
        yes_ask=72,
        title="A",
        volume_usd_24h=Decimal("500"),
    )

    kalshi_ds = AsyncMock()
    kalshi_ds.get_events.return_value = [k_market]
    polymarket_ds = AsyncMock()
    polymarket_ds.get_events.return_value = [p_market]

    spread_store = AsyncMock()
    spread_store.record = AsyncMock(return_value=99)

    event_bus = AsyncMock()
    event_bus.publish = AsyncMock(side_effect=RuntimeError("redis down"))

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

    agent = CrossPlatformArbAgent(
        _make_config(),
        kalshi_ds=kalshi_ds,
        polymarket_ds=polymarket_ds,
        spread_store=spread_store,
        event_bus=event_bus,
    )
    opps = await agent.scan(data=MagicMock())

    # Opportunity still emitted despite the publish failure
    assert len(opps) == 1
    # Publish was attempted
    assert event_bus.publish.await_count == 1
