"""
Kalshi pipeline integration tests.

Exercises: KalshiCalibrationAgent.scan → OpportunityRouter → RiskEngine → KalshiPaperBroker.

Marked @pytest.mark.live_paper — not run in normal CI.
Requires: STA_KALSHI_DEMO=true (set to prevent accidental production runs).
Actual API credentials are optional; tests that need them are gated by skip_no_kalshi.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


pytestmark = [
    pytest.mark.live_paper,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(name: str = "kalshi_calibration_test"):
    """Build a KalshiCalibrationAgent with minimal config."""
    from agents.models import ActionLevel, AgentConfig
    from strategies.kalshi_calibration import KalshiCalibrationAgent

    config = AgentConfig(
        name=name,
        strategy="kalshi_calibration",
        schedule="on_demand",
        action_level=ActionLevel.AUTO_EXECUTE,
        parameters={
            "threshold_cents": 5,
            "min_volume": 0,
            "max_markets": 20,
        },
    )
    return KalshiCalibrationAgent(config)


def _make_mock_data_bus(kalshi_source):
    """Minimal DataBus with a KalshiDataSource attached."""
    bus = MagicMock()
    bus._kalshi_source = kalshi_source
    bus._settings = None
    return bus


async def _build_router(live_db, broker):
    """Wire up a minimal OpportunityRouter with risk engine and paper broker."""

    from notifications.log_notifier import LogNotifier
    from risk.engine import RiskEngine
    from risk.kill_switch import KillSwitch
    from risk.rules import MaxPositionSize
    from storage.opportunities import OpportunityStore

    store = OpportunityStore(live_db)
    notifier = LogNotifier()
    kill_switch = KillSwitch()
    risk_engine = RiskEngine(
        rules=[MaxPositionSize(max_dollars=1000.0, max_shares=100)],
        kill_switch=kill_switch,
    )

    from agents.router import OpportunityRouter

    return OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
    )


# ---------------------------------------------------------------------------
# Test 1 — Agent scan produces a list (may be empty if no Metaculus matches)
# ---------------------------------------------------------------------------


@pytest.mark.timeout(60)
async def test_kalshi_agent_scan_returns_list(kalshi_client):
    """
    KalshiCalibrationAgent.scan() with a real KalshiDataSource returns a list.
    The list may be empty if the demo API has no markets or Metaculus finds no
    match above the similarity threshold — that is still a valid result.
    """
    from adapters.kalshi.data_source import KalshiDataSource

    agent = _make_agent()
    ds = KalshiDataSource(kalshi_client)
    bus = _make_mock_data_bus(ds)

    opportunities = await agent.scan(bus)

    assert isinstance(opportunities, list)
    for opp in opportunities:
        assert opp.agent_name == agent.name
        assert opp.symbol is not None
        assert 0.0 <= opp.confidence <= 1.0


# ---------------------------------------------------------------------------
# Test 2 — Router saves opportunity to store (no broker needed)
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
async def test_router_saves_opportunity_to_store(live_db, kalshi_paper_broker):
    """
    OpportunityRouter.route() with ActionLevel.NOTIFY stores the opportunity in
    the DB but does not attempt order execution.
    """
    import uuid
    from datetime import datetime, timezone

    from agents.models import ActionLevel, Opportunity, OpportunityStatus
    from broker.models import AssetType, LimitOrder, OrderSide, Symbol, TIF
    from storage.opportunities import OpportunityStore

    sym = Symbol(ticker="KXTEST-12345-YES", asset_type=AssetType.PREDICTION)
    opp = Opportunity(
        id=str(uuid.uuid4()),
        agent_name="kalshi_calibration_test",
        symbol=sym,
        signal="YES",
        confidence=0.65,
        reasoning="Unit test opportunity",
        data={"kalshi_ticker": "KXTEST-12345-YES"},
        timestamp=datetime.now(timezone.utc),
        status=OpportunityStatus.PENDING,
        suggested_trade=LimitOrder(
            symbol=sym,
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            account_id="KALSHI",
            limit_price=Decimal("0.45"),
            time_in_force=TIF.GTC,
        ),
    )

    router = await _build_router(live_db, kalshi_paper_broker)
    await router.route(opp, ActionLevel.NOTIFY)

    store = OpportunityStore(live_db)
    saved = await store.get(opp.id)
    assert saved is not None
    assert saved["agent_name"] == "kalshi_calibration_test"


# ---------------------------------------------------------------------------
# Test 3 — Full AUTO_EXECUTE path reaches paper broker and gets FILLED
# ---------------------------------------------------------------------------


@pytest.mark.timeout(60)
async def test_auto_execute_fills_via_paper_broker(
    live_db, kalshi_paper_broker, kalshi_client
):
    """
    An AUTO_EXECUTE opportunity with a passing risk check should be routed
    all the way to KalshiPaperBroker and return an EXECUTED status in the store.

    We inject a mock DataBus that returns a valid Quote so the risk engine can
    evaluate the trade (no real price fetch required).
    """
    import uuid
    from datetime import datetime, timezone

    from agents.models import ActionLevel, Opportunity, OpportunityStatus
    from broker.models import (
        AccountBalance,
        AssetType,
        LimitOrder,
        OrderSide,
        Quote,
        Symbol,
        TIF,
    )
    from storage.opportunities import OpportunityStore

    # Grab a real ticker so the paper broker looks up real market data
    page = await kalshi_client.get_markets(status="open", limit=1)
    markets = page.get("markets", [])
    if not markets:
        pytest.skip(
            "No open markets returned by Kalshi demo — cannot test auto-execute"
        )

    ticker = markets[0]["ticker"]
    sym = Symbol(ticker=ticker, asset_type=AssetType.PREDICTION)

    # Mock DataBus that returns a plausible Quote and empty positions/balance
    mock_bus = MagicMock()
    mock_bus.get_quote = AsyncMock(
        return_value=Quote(
            symbol=sym, bid=Decimal("0.40"), ask=Decimal("0.42"), last=Decimal("0.41")
        )
    )
    mock_bus.get_positions = AsyncMock(return_value=[])
    mock_bus.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id="KALSHI",
            net_liquidation=Decimal("10000"),
            buying_power=Decimal("10000"),
            cash=Decimal("10000"),
            maintenance_margin=Decimal("0"),
        )
    )

    from notifications.log_notifier import LogNotifier
    from risk.engine import RiskEngine
    from risk.kill_switch import KillSwitch
    from risk.rules import MaxPositionSize
    from agents.router import OpportunityRouter

    store = OpportunityStore(live_db)
    router = OpportunityRouter(
        store=store,
        notifier=LogNotifier(),
        risk_engine=RiskEngine(
            rules=[MaxPositionSize(max_dollars=500.0, max_shares=50)],
            kill_switch=KillSwitch(),
        ),
        broker=kalshi_paper_broker,
        data_bus=mock_bus,
    )

    from adapters.kalshi.paper import KALSHI_PAPER_ACCOUNT_ID

    opp_id = str(uuid.uuid4())
    opp = Opportunity(
        id=opp_id,
        agent_name="kalshi_calibration_test",
        symbol=sym,
        signal="YES",
        confidence=0.70,
        reasoning="Pipeline auto-execute test",
        data={},
        timestamp=datetime.now(timezone.utc),
        status=OpportunityStatus.PENDING,
        broker_id="kalshi",
        suggested_trade=LimitOrder(
            symbol=sym,
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            account_id=KALSHI_PAPER_ACCOUNT_ID,
            limit_price=Decimal("0.41"),
            time_in_force=TIF.GTC,
        ),
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    saved = await store.get(opp_id)
    assert saved is not None
    assert saved["status"] == OpportunityStatus.EXECUTED.value


# ---------------------------------------------------------------------------
# Test 4 — Risk engine blocks an oversized order
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
async def test_risk_engine_blocks_oversized_order(live_db, kalshi_paper_broker):
    """
    A trade that exceeds MaxPositionSize must be blocked (status → REJECTED)
    and must NOT result in a paper order fill.
    """
    import uuid
    from datetime import datetime, timezone

    from agents.models import ActionLevel, Opportunity, OpportunityStatus
    from broker.models import (
        AccountBalance,
        AssetType,
        LimitOrder,
        OrderSide,
        Quote,
        Symbol,
        TIF,
    )
    from storage.opportunities import OpportunityStore

    sym = Symbol(ticker="KXBIG-99999-YES", asset_type=AssetType.PREDICTION)

    # DataBus returns a quote so risk engine can evaluate dollar value
    mock_bus = MagicMock()
    mock_bus.get_quote = AsyncMock(
        return_value=Quote(
            symbol=sym, bid=Decimal("0.50"), ask=Decimal("0.52"), last=Decimal("0.51")
        )
    )
    mock_bus.get_positions = AsyncMock(return_value=[])
    mock_bus.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id="KALSHI",
            net_liquidation=Decimal("10000"),
            buying_power=Decimal("10000"),
            cash=Decimal("10000"),
            maintenance_margin=Decimal("0"),
        )
    )

    from notifications.log_notifier import LogNotifier
    from risk.engine import RiskEngine
    from risk.kill_switch import KillSwitch
    from risk.rules import MaxPositionSize
    from agents.router import OpportunityRouter

    store = OpportunityStore(live_db)
    # Tight max: $1 max dollars — 1000 contracts * $0.51 will definitely exceed this
    router = OpportunityRouter(
        store=store,
        notifier=LogNotifier(),
        risk_engine=RiskEngine(
            rules=[MaxPositionSize(max_dollars=1.0, max_shares=1)],
            kill_switch=KillSwitch(),
        ),
        broker=kalshi_paper_broker,
        data_bus=mock_bus,
    )

    opp_id = str(uuid.uuid4())
    opp = Opportunity(
        id=opp_id,
        agent_name="kalshi_calibration_test",
        symbol=sym,
        signal="YES",
        confidence=0.80,
        reasoning="Oversized order — should be blocked",
        data={},
        timestamp=datetime.now(timezone.utc),
        status=OpportunityStatus.PENDING,
        suggested_trade=LimitOrder(
            symbol=sym,
            side=OrderSide.BUY,
            quantity=Decimal("1000"),  # far exceeds max_shares=1
            account_id="KALSHI",
            limit_price=Decimal("0.51"),
            time_in_force=TIF.GTC,
        ),
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    saved = await store.get(opp_id)
    assert saved is not None
    assert saved["status"] == OpportunityStatus.REJECTED.value
