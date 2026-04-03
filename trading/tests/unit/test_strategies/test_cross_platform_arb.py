"""Tests for CrossPlatformArbAgent."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from agents.models import ActionLevel, AgentConfig, OpportunityStatus
from broker.models import AssetType, PredictionContract, Symbol


def _make_config(params=None):
    return AgentConfig(
        name="cross_platform_arb",
        strategy="cross_platform_arb",
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        parameters=params or {},
    )


def _make_contract(ticker, title, yes_bid=None, yes_ask=None, yes_last=None, volume_24h=1000):
    return PredictionContract(
        ticker=ticker,
        title=title,
        category="politics",
        close_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        yes_last=yes_last,
        volume_24h=volume_24h,
    )


def _make_ds(contracts):
    ds = MagicMock()
    ds.get_markets = AsyncMock(return_value=contracts)
    return ds


@pytest.fixture
def kalshi_ds():
    return _make_ds([
        _make_contract("KALSHI-001", "Will inflation fall below 3% in 2026?", yes_bid=60, yes_ask=62),
        _make_contract("KALSHI-002", "Will the Fed cut rates in Q2 2026?", yes_bid=40, yes_ask=42),
    ])


@pytest.fixture
def poly_ds():
    return _make_ds([
        _make_contract("poly-cond-001", "Will inflation drop below 3% in 2026?", yes_bid=74, yes_ask=76),
        _make_contract("poly-cond-002", "Will the Federal Reserve cut interest rates Q2 2026?", yes_bid=41, yes_ask=43),
    ])


@pytest.fixture
def agent(kalshi_ds, poly_ds):
    from strategies.cross_platform_arb import CrossPlatformArbAgent
    config = _make_config({"threshold_cents": 8, "min_match_similarity": 0.4})
    return CrossPlatformArbAgent(config=config, kalshi_ds=kalshi_ds, polymarket_ds=poly_ds)


@pytest.mark.asyncio
async def test_opportunity_emitted_when_gap_exceeds_threshold(agent):
    """Gap > threshold_cents → opportunity emitted targeting cheaper venue."""
    opps = await agent.scan(MagicMock())
    # KALSHI-001 (mid=61¢) vs poly-cond-001 (mid=75¢) → 14¢ gap > 8¢ threshold
    assert len(opps) >= 1
    gaps = [o.data["gap_cents"] for o in opps]
    assert any(g > 8 for g in gaps)


@pytest.mark.asyncio
async def test_broker_id_matches_target_venue(agent):
    """broker_id on emitted Opportunity matches the cheaper venue."""
    opps = await agent.scan(MagicMock())
    for opp in opps:
        assert opp.broker_id in ("kalshi", "polymarket")
        assert opp.data["target_broker"] == opp.broker_id


@pytest.mark.asyncio
async def test_cheaper_venue_is_target(agent):
    """The opportunity targets the venue with the lower price (buy there)."""
    opps = await agent.scan(MagicMock())
    big_gap = [o for o in opps if o.data["gap_cents"] > 8]
    assert big_gap
    opp = big_gap[0]
    k_cents = opp.data["kalshi_cents"]
    p_cents = opp.data["polymarket_cents"]
    if k_cents < p_cents:
        assert opp.broker_id == "kalshi"
        assert opp.suggested_trade.account_id == "KALSHI"
    else:
        assert opp.broker_id == "polymarket"
        assert opp.suggested_trade.account_id == "POLYMARKET"


@pytest.mark.asyncio
async def test_no_opportunity_when_below_threshold():
    """Gap <= threshold_cents → no opportunity emitted."""
    kalshi_ds = _make_ds([
        _make_contract("K-001", "Will event X happen in 2026?", yes_bid=50, yes_ask=52),
    ])
    poly_ds = _make_ds([
        _make_contract("p-001", "Will event X happen in 2026?", yes_bid=54, yes_ask=56),
    ])
    from strategies.cross_platform_arb import CrossPlatformArbAgent
    config = _make_config({"threshold_cents": 8, "min_match_similarity": 0.5})
    agent = CrossPlatformArbAgent(config=config, kalshi_ds=kalshi_ds, polymarket_ds=poly_ds)
    opps = await agent.scan(MagicMock())
    # Gap is ~5¢ (mid 51 vs 55), below threshold of 8
    assert opps == []


@pytest.mark.asyncio
async def test_no_opportunity_when_same_price():
    """Tie-breaking: identical prices → no opportunity."""
    kalshi_ds = _make_ds([
        _make_contract("K-001", "Will the same thing happen?", yes_bid=65, yes_ask=65),
    ])
    poly_ds = _make_ds([
        _make_contract("p-001", "Will the same thing happen?", yes_bid=65, yes_ask=65),
    ])
    from strategies.cross_platform_arb import CrossPlatformArbAgent
    config = _make_config({"threshold_cents": 0, "min_match_similarity": 0.5})
    agent = CrossPlatformArbAgent(config=config, kalshi_ds=kalshi_ds, polymarket_ds=poly_ds)
    opps = await agent.scan(MagicMock())
    assert opps == []


@pytest.mark.asyncio
async def test_fuzzy_match_respects_min_similarity():
    """Pairs below min_match_similarity are not matched."""
    kalshi_ds = _make_ds([
        _make_contract("K-001", "Will inflation fall in 2026?", yes_bid=60, yes_ask=62),
    ])
    poly_ds = _make_ds([
        _make_contract("p-001", "Basketball championship winner 2026?", yes_bid=10, yes_ask=12),
    ])
    from strategies.cross_platform_arb import CrossPlatformArbAgent
    config = _make_config({"threshold_cents": 5, "min_match_similarity": 0.75})
    agent = CrossPlatformArbAgent(config=config, kalshi_ds=kalshi_ds, polymarket_ds=poly_ds)
    opps = await agent.scan(MagicMock())
    assert opps == []


@pytest.mark.asyncio
async def test_no_opportunity_when_data_source_missing():
    """Missing data sources → empty result, no crash."""
    from strategies.cross_platform_arb import CrossPlatformArbAgent
    config = _make_config()
    agent = CrossPlatformArbAgent(config=config, kalshi_ds=None, polymarket_ds=None)
    # DataBus with no _kalshi_source / _polymarket_source attrs
    data_bus = MagicMock(spec=[])
    opps = await agent.scan(data_bus)
    assert opps == []


@pytest.mark.asyncio
async def test_opportunity_status_is_pending(agent):
    """Emitted opportunities start as PENDING."""
    opps = await agent.scan(MagicMock())
    for opp in opps:
        assert opp.status == OpportunityStatus.PENDING


@pytest.mark.asyncio
async def test_suggested_trade_is_limit_order_on_target(agent):
    """Suggested trade is a LimitOrder pointing at the target symbol/account."""
    from broker.models import LimitOrder
    opps = await agent.scan(MagicMock())
    for opp in opps:
        trade = opp.suggested_trade
        assert isinstance(trade, LimitOrder)
        assert trade.symbol == opp.symbol
        expected_account = "KALSHI" if opp.broker_id == "kalshi" else "POLYMARKET"
        assert trade.account_id == expected_account


@pytest.mark.asyncio
async def test_scan_uses_ask_price_for_kalshi():
    """CrossPlatformArbAgent should use yes_ask for Kalshi leg in spread calc."""
    import aiosqlite
    from storage.db import init_db
    from storage.spreads import SpreadStore
    from strategies.cross_platform_arb import CrossPlatformArbAgent
    from datetime import timedelta

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    store = SpreadStore(db)

    k_contract = _make_contract("KASK", "Will the Fed raise rates?", yes_bid=38, yes_ask=42, volume_24h=1000)
    p_contract = _make_contract("PASK", "Will the Fed raise rates?", yes_bid=60, yes_ask=62, volume_24h=5000)

    config = AgentConfig(
        name="test_arb_ask", strategy="cross_platform_arb", schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
        parameters={"threshold_cents": 3, "min_match_similarity": 0.0, "max_markets_per_platform": 5},
    )

    kalshi_ds = _make_ds([k_contract])
    poly_ds = _make_ds([p_contract])

    agent = CrossPlatformArbAgent(config, kalshi_ds=kalshi_ds, polymarket_ds=poly_ds)
    agent.spread_store = store

    await agent.scan(MagicMock())

    history = await store.get_history("KASK", "PASK", hours=1)
    assert len(history) >= 1
    assert history[0].kalshi_cents == 42, f"Expected 42 (ask), got {history[0].kalshi_cents}"
    await db.close()


@pytest.mark.asyncio
async def test_scan_records_spread_observation():
    """scan() persists a SpreadObservation for every matched pair via SpreadStore."""
    import aiosqlite
    from storage.db import init_db
    from storage.spreads import SpreadStore
    from strategies.cross_platform_arb import CrossPlatformArbAgent

    kalshi_ds = _make_ds([
        _make_contract("KALSHI-001", "Will inflation fall below 3% in 2026?", yes_bid=60, yes_ask=62, volume_24h=5000),
    ])
    poly_ds = _make_ds([
        _make_contract("poly-cond-001", "Will inflation drop below 3% in 2026?", yes_bid=74, yes_ask=76, volume_24h=4000),
    ])

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    spread_store = SpreadStore(db)

    config = _make_config({"threshold_cents": 8, "min_match_similarity": 0.4})
    agent = CrossPlatformArbAgent(
        config=config,
        kalshi_ds=kalshi_ds,
        polymarket_ds=poly_ds,
        spread_store=spread_store,
    )

    await agent.scan(MagicMock())

    history = await spread_store.get_history("KALSHI-001", "poly-cond-001", hours=1)
    assert len(history) >= 1

    await db.close()
