"""
Polymarket pipeline integration tests.

Exercises: PolymarketCalibrationAgent.scan → OpportunityRouter → dry-run execution.

Marked @pytest.mark.live_paper — not run in normal CI.
Requires: STA_POLYMARKET_DRY_RUN=true (set to prevent accidental live order submission).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.live_paper.conftest import skip_no_polymarket

pytestmark = [
    pytest.mark.live_paper,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(name: str = "polymarket_calibration_test"):
    """Build a PolymarketCalibrationAgent with permissive config."""
    from agents.models import ActionLevel, AgentConfig
    from strategies.polymarket_calibration import PolymarketCalibrationAgent

    config = AgentConfig(
        name=name,
        strategy="polymarket_calibration",
        schedule="on_demand",
        action_level=ActionLevel.AUTO_EXECUTE,
        parameters={
            "threshold_cents": 5,
            "max_markets_per_scan": 5,
            "tags": ["politics"],
            "min_match_similarity": 0.5,
        },
    )
    return PolymarketCalibrationAgent(config)


def _make_mock_data_bus(polymarket_source):
    """Minimal DataBus with a PolymarketDataSource attached."""
    bus = MagicMock()
    bus._polymarket_source = polymarket_source
    return bus


# ---------------------------------------------------------------------------
# Test 1 — Calibration agent scan with real Polymarket data
# ---------------------------------------------------------------------------


@skip_no_polymarket
@pytest.mark.timeout(60)
async def test_polymarket_calibration_agent_scan(polymarket_client):
    """
    PolymarketCalibrationAgent.scan() with a real PolymarketDataSource returns
    a list. May be empty if no external probability matches exist — that is a
    valid result since Manifold/Metaculus queries may find no similar questions.
    """
    from adapters.polymarket.data_source import PolymarketDataSource

    agent = _make_agent()
    ds = PolymarketDataSource(polymarket_client)
    bus = _make_mock_data_bus(ds)

    opportunities = await agent.scan(bus)

    assert isinstance(opportunities, list)
    for opp in opportunities:
        assert opp.agent_name == agent.name
        assert opp.symbol is not None
        assert 0.0 <= opp.confidence <= 1.0
        assert opp.broker_id == "polymarket"


# ---------------------------------------------------------------------------
# Test 2 — Dry-run execution pipeline completes without error
# ---------------------------------------------------------------------------


@skip_no_polymarket
@pytest.mark.timeout(60)
async def test_dry_run_execution_pipeline(
    live_db, polymarket_broker, polymarket_client
):
    """
    An AUTO_EXECUTE opportunity routed through OpportunityRouter reaches the
    PolymarketBroker(dry_run=True) and returns EXECUTED status.

    Uses a real token_id from the Polymarket CLOB so the order shape is valid.
    """
    import uuid
    from datetime import datetime, timezone

    from adapters.polymarket.broker import PolymarketAccount
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
    from notifications.log_notifier import LogNotifier
    from risk.engine import RiskEngine
    from risk.kill_switch import KillSwitch
    from risk.rules import MaxPredictionExposure
    from storage.opportunities import OpportunityStore
    from agents.router import OpportunityRouter

    # Fetch a real market token to build a valid order
    data = polymarket_client.get_markets(active=True, limit=2)
    markets = data.get("data", []) if isinstance(data, dict) else data
    if not markets:
        pytest.skip("No active Polymarket markets for pipeline test")
    tokens = markets[0].get("tokens", [])
    if not tokens:
        pytest.skip("First market has no tokens for pipeline test")
    token_id = tokens[0].get("token_id") or tokens[0].get("tokenId")

    sym = Symbol(ticker=token_id, asset_type=AssetType.PREDICTION)

    # Mock DataBus with a valid quote and sufficient balance
    mock_bus = MagicMock()
    mock_bus.get_quote = AsyncMock(
        return_value=Quote(
            symbol=sym, bid=Decimal("0.45"), ask=Decimal("0.47"), last=Decimal("0.46")
        )
    )
    mock_bus.get_positions = AsyncMock(return_value=[])
    mock_bus.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id=PolymarketAccount.ACCOUNT_ID,
            net_liquidation=Decimal("10000"),
            buying_power=Decimal("10000"),
            cash=Decimal("10000"),
            maintenance_margin=Decimal("0"),
        )
    )

    store = OpportunityStore(live_db)
    router = OpportunityRouter(
        store=store,
        notifier=LogNotifier(),
        risk_engine=RiskEngine(
            rules=[MaxPredictionExposure(max_dollars=500.0)],
            kill_switch=KillSwitch(),
        ),
        broker=polymarket_broker,
        brokers={"polymarket": polymarket_broker},
        data_bus=mock_bus,
    )

    opp_id = str(uuid.uuid4())
    opp = Opportunity(
        id=opp_id,
        agent_name="polymarket_calibration_test",
        symbol=sym,
        signal="BUY",
        confidence=0.60,
        reasoning="Dry-run pipeline test",
        data={},
        timestamp=datetime.now(timezone.utc),
        status=OpportunityStatus.PENDING,
        broker_id="polymarket",
        suggested_trade=LimitOrder(
            symbol=sym,
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id=PolymarketAccount.ACCOUNT_ID,
            limit_price=Decimal("0.46"),
            time_in_force=TIF.GTC,
        ),
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    saved = await store.get(opp_id)
    assert saved is not None
    assert saved["status"] == OpportunityStatus.EXECUTED.value


# ---------------------------------------------------------------------------
# Test 3 — Data source quote feeds risk check (no credentials required)
# ---------------------------------------------------------------------------


@skip_no_polymarket
@pytest.mark.timeout(30)
async def test_risk_check_uses_data_source_quote(live_db, polymarket_broker):
    """
    When a Quote cannot be fetched (data bus returns None), the risk check
    must reject the opportunity rather than crash.
    """
    import uuid
    from datetime import datetime, timezone

    from adapters.polymarket.broker import PolymarketAccount
    from agents.models import ActionLevel, Opportunity, OpportunityStatus
    from broker.models import AssetType, LimitOrder, OrderSide, Symbol, TIF
    from notifications.log_notifier import LogNotifier
    from risk.engine import RiskEngine
    from risk.kill_switch import KillSwitch
    from risk.rules import MaxPredictionExposure
    from storage.opportunities import OpportunityStore
    from agents.router import OpportunityRouter

    sym = Symbol(ticker="0xDEAD", asset_type=AssetType.PREDICTION)

    # DataBus returns None quote → router must reject gracefully
    mock_bus = MagicMock()
    mock_bus.get_quote = AsyncMock(return_value=None)
    mock_bus.get_positions = AsyncMock(return_value=[])
    mock_bus.get_balances = AsyncMock(return_value=None)

    store = OpportunityStore(live_db)
    router = OpportunityRouter(
        store=store,
        notifier=LogNotifier(),
        risk_engine=RiskEngine(
            rules=[MaxPredictionExposure(max_dollars=100.0)],
            kill_switch=KillSwitch(),
        ),
        broker=polymarket_broker,
        data_bus=mock_bus,
    )

    opp_id = str(uuid.uuid4())
    opp = Opportunity(
        id=opp_id,
        agent_name="polymarket_calibration_test",
        symbol=sym,
        signal="BUY",
        confidence=0.50,
        reasoning="No-quote rejection test",
        data={},
        timestamp=datetime.now(timezone.utc),
        status=OpportunityStatus.PENDING,
        suggested_trade=LimitOrder(
            symbol=sym,
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id=PolymarketAccount.ACCOUNT_ID,
            limit_price=Decimal("0.50"),
            time_in_force=TIF.GTC,
        ),
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    saved = await store.get(opp_id)
    assert saved is not None
    assert saved["status"] == OpportunityStatus.REJECTED.value
