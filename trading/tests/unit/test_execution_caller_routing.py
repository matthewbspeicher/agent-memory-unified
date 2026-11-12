"""Caller routing must preserve the selected broker's real account identity."""

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import APIRouter, FastAPI, HTTPException
import pytest

from api.routes.arbitrage import ExecuteArbRequest, execute_arbitrage
from broker.models import Account, LimitOrder, OrderSide
from execution.models import ArbState


def request_rig(paper=True):
    brokers = {
        name: SimpleNamespace(
            account=SimpleNamespace(
                get_accounts=AsyncMock(return_value=[Account(account)])
            )
        )
        for name, account in (
            ("kalshi", "discovered-kalshi"),
            ("polymarket", "discovered-poly"),
            ("kalshi_paper", "KALSHI_PAPER"),
            ("polymarket_paper", "POLYMARKET_PAPER"),
        )
    }

    async def execute(trade):
        trade.state = ArbState.COMPLETED
        return True

    coordinator = SimpleNamespace(
        _brokers=brokers, execute_arbitrage=AsyncMock(side_effect=execute)
    )
    spreads = SimpleNamespace(
        claim_spread=AsyncMock(return_value=True),
        release_spread=AsyncMock(),
        get_observation=AsyncMock(
            return_value={
                "kalshi_ticker": "K-YES",
                "poly_ticker": "P-YES",
                "kalshi_cents": 45,
                "poly_cents": 55,
                "gap_cents": 10,
            }
        ),
    )
    state = SimpleNamespace(
        config=SimpleNamespace(paper_trading=paper),
        arb_coordinator=coordinator,
        spread_store=spreads,
    )
    return SimpleNamespace(
        request=SimpleNamespace(app=SimpleNamespace(state=state)),
        coordinator=coordinator,
        spreads=spreads,
        brokers=brokers,
    )


@pytest.mark.parametrize("paper", [True, False])
async def test_manual_arb_uses_selected_brokers_accounts_and_observed_limit_prices(
    paper,
):
    rig = request_rig(paper)
    result = await execute_arbitrage(
        ExecuteArbRequest(observation_id=1, agent_name="test"), rig.request
    )
    assert result["status"] == "completed"
    trade = rig.coordinator.execute_arbitrage.await_args.args[0]
    assert isinstance(trade.leg_a.order, LimitOrder)
    assert isinstance(trade.leg_b.order, LimitOrder)
    assert (trade.leg_a.order.limit_price, trade.leg_b.order.limit_price) == (
        Decimal("0.45"),
        Decimal("0.55"),
    )
    assert (trade.leg_a.order.side, trade.leg_b.order.side) == (
        OrderSide.BUY,
        OrderSide.SELL,
    )
    if paper:
        assert (trade.leg_a.broker_id, trade.leg_b.broker_id) == (
            "kalshi_paper",
            "polymarket_paper",
        )
        assert (trade.leg_a.order.account_id, trade.leg_b.order.account_id) == (
            "KALSHI_PAPER",
            "POLYMARKET_PAPER",
        )
        rig.brokers["kalshi"].account.get_accounts.assert_not_awaited()
        rig.brokers["polymarket"].account.get_accounts.assert_not_awaited()
    else:
        assert (trade.leg_a.broker_id, trade.leg_b.broker_id) == (
            "kalshi",
            "polymarket",
        )
        assert (trade.leg_a.order.account_id, trade.leg_b.order.account_id) == (
            "discovered-kalshi",
            "discovered-poly",
        )


async def test_manual_paper_arb_never_falls_back_to_live_broker():
    rig = request_rig(True)
    del rig.brokers["kalshi_paper"]
    with pytest.raises(HTTPException) as exc:
        await execute_arbitrage(
            ExecuteArbRequest(observation_id=1, agent_name="test"), rig.request
        )
    assert exc.value.status_code == 503
    rig.coordinator.execute_arbitrage.assert_not_awaited()
    rig.spreads.claim_spread.assert_not_awaited()
    rig.brokers["kalshi"].account.get_accounts.assert_not_awaited()


@pytest.mark.parametrize("price", [None, "NaN", 0, 101])
async def test_manual_arb_does_not_invent_missing_or_invalid_observed_price(price):
    rig = request_rig(True)
    rig.spreads.get_observation.return_value["kalshi_cents"] = price
    with pytest.raises(HTTPException) as exc:
        await execute_arbitrage(
            ExecuteArbRequest(observation_id=1, agent_name="test"), rig.request
        )
    assert exc.value.status_code == 422
    rig.coordinator.execute_arbitrage.assert_not_awaited()
    rig.spreads.release_spread.assert_awaited_once_with(1)


async def test_manual_arb_missing_observation_preserves_404_and_releases_once():
    rig = request_rig(True)
    rig.spreads.get_observation.return_value = None
    with pytest.raises(HTTPException) as exc:
        await execute_arbitrage(
            ExecuteArbRequest(observation_id=1, agent_name="test"), rig.request
        )
    assert exc.value.status_code == 404
    rig.spreads.release_spread.assert_awaited_once_with(1)


async def test_manual_live_account_ambiguity_is_not_guessed():
    rig = request_rig(False)
    rig.brokers["kalshi"].account.get_accounts.return_value = [
        Account("one"),
        Account("two"),
    ]
    with pytest.raises(HTTPException) as exc:
        await execute_arbitrage(
            ExecuteArbRequest(observation_id=1, agent_name="test"), rig.request
        )
    assert exc.value.status_code == 503
    rig.coordinator.execute_arbitrage.assert_not_awaited()
    rig.spreads.claim_spread.assert_not_awaited()


@pytest.mark.parametrize("account_id", ["PAPER", "configured-primary-account", ""])
def test_whatsapp_setup_receives_resolved_primary_account_without_default_guess(
    monkeypatch, account_id
):
    from api.app import _setup_whatsapp_routes
    from config import Config

    app = FastAPI()
    app.state.execution_service = object()
    assistant_factory = MagicMock()
    monkeypatch.setattr("whatsapp.assistant.WhatsAppAssistant", assistant_factory)
    monkeypatch.setattr(
        "whatsapp.webhook.create_webhook_router", lambda **kwargs: APIRouter()
    )
    broker = MagicMock()
    _setup_whatsapp_routes(
        app=app,
        config=Config(paper_trading=account_id == "PAPER"),
        wa_client=MagicMock(),
        wa_numbers=[],
        broker=broker,
        account_id=account_id,
        runner=MagicMock(),
        opp_store=MagicMock(),
        risk_engine=MagicMock(),
        llm_client=None,
        ext_store=None,
        data_bus=None,
        leaderboard_engine=None,
        journal_service=None,
        brief_generator=None,
        warroom_engine=None,
        db=None,
        agent_store=None,
        logger=logging.getLogger(__name__),
    )
    assert assistant_factory.call_args.kwargs["account_id"] == account_id
    assert assistant_factory.call_args.kwargs["broker"] is broker
    assert (
        assistant_factory.call_args.kwargs["execution_service"]
        is app.state.execution_service
    )
