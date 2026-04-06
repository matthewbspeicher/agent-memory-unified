"""Tests for regime stamping and static gating in OpportunityRouter."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.models import (
    ActionLevel,
    AgentConfig,
    Opportunity,
    OpportunityStatus,
)
from agents.router import OpportunityRouter
from broker.models import AssetType, Symbol


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_symbol(ticker: str = "AAPL") -> Symbol:
    return Symbol(ticker=ticker, asset_type=AssetType.STOCK)


def _make_opportunity(
    agent_name: str = "test_agent", ticker: str = "AAPL"
) -> Opportunity:
    return Opportunity(
        id=str(uuid.uuid4()),
        agent_name=agent_name,
        symbol=_make_symbol(ticker),
        signal="buy",
        confidence=0.8,
        reasoning="test",
        data={},
        timestamp=datetime.now(timezone.utc),
    )


def _make_router(**kwargs) -> OpportunityRouter:
    store = AsyncMock()
    store.save = AsyncMock()
    store.save_snapshot = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()
    notifier.send = AsyncMock()
    return OpportunityRouter(store=store, notifier=notifier, **kwargs)


def _make_agent_with_config(
    name: str = "test_agent",
    regime_policy_mode: str = "annotate_only",
    allowed_regimes: dict | None = None,
    disallowed_regimes: dict | None = None,
) -> MagicMock:
    cfg = AgentConfig(
        name=name,
        strategy="rsi",
        schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
        regime_policy_mode=regime_policy_mode,
        allowed_regimes=allowed_regimes or {},
        disallowed_regimes=disallowed_regimes or {},
    )
    agent = MagicMock()
    agent.name = name
    agent.config = cfg
    return agent


def _make_runner_with_agent(agent: MagicMock) -> MagicMock:
    runner = MagicMock()
    runner.get_agent = MagicMock(return_value=agent)
    return runner


# ---------------------------------------------------------------------------
# Regime stamping — all action levels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regime_stamped_on_notify():
    """NOTIFY action level should still get regime stamped in opportunity.data."""
    opp = _make_opportunity()
    router = _make_router()

    with patch(
        "agents.router.OpportunityRouter._stamp_regime", new_callable=AsyncMock
    ) as mock_stamp:

        async def _fake_stamp(opportunity):
            opportunity.data["regime"] = {
                "trend_regime": "uptrend",
                "volatility_regime": "medium",
            }

        mock_stamp.side_effect = _fake_stamp

        await router.route(opp, ActionLevel.NOTIFY)

    assert "regime" in opp.data
    assert opp.data["regime"]["trend_regime"] == "uptrend"


@pytest.mark.asyncio
async def test_regime_stamped_on_suggest_trade():
    """SUGGEST_TRADE action level should still get regime stamped."""
    opp = _make_opportunity()
    router = _make_router()

    with patch(
        "agents.router.OpportunityRouter._stamp_regime", new_callable=AsyncMock
    ) as mock_stamp:

        async def _fake_stamp(opportunity):
            opportunity.data["regime"] = {"trend_regime": "range"}

        mock_stamp.side_effect = _fake_stamp

        await router.route(opp, ActionLevel.SUGGEST_TRADE)

    assert opp.data.get("regime", {}).get("trend_regime") == "range"


@pytest.mark.asyncio
async def test_regime_stamp_fails_open():
    """A regime stamping failure must not block routing."""
    opp = _make_opportunity()
    router = _make_router()

    with patch(
        "agents.router.OpportunityRouter._stamp_regime", new_callable=AsyncMock
    ) as mock_stamp:
        mock_stamp.side_effect = Exception("data bus down")

        # Should not raise even though stamp fails
        await router.route(opp, ActionLevel.NOTIFY)

    # data should be unchanged (empty)
    assert opp.data.get("regime") is None


# ---------------------------------------------------------------------------
# annotate_only mode — never blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_annotate_only_never_blocks():
    """annotate_only mode stamps regime but never rejects the opportunity."""
    opp = _make_opportunity()
    opp.data["regime"] = {"trend_regime": "uptrend", "volatility_regime": "high"}

    agent = _make_agent_with_config(
        regime_policy_mode="annotate_only",
        disallowed_regimes={"volatility_regime": ["high"]},
    )
    runner = _make_runner_with_agent(agent)
    router = _make_router(runner=runner)

    with patch("agents.router.OpportunityRouter._stamp_regime", new_callable=AsyncMock):
        await router.route(opp, ActionLevel.NOTIFY)

    # Should NOT be rejected
    router._store.update_status.assert_not_called()


# ---------------------------------------------------------------------------
# off mode — no check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_off_mode_no_check():
    """off mode skips all regime policy checks."""
    opp = _make_opportunity()
    opp.data["regime"] = {"trend_regime": "downtrend", "volatility_regime": "high"}

    agent = _make_agent_with_config(
        regime_policy_mode="off",
        disallowed_regimes={
            "trend_regime": ["downtrend"],
            "volatility_regime": ["high"],
        },
    )
    runner = _make_runner_with_agent(agent)
    router = _make_router(runner=runner)

    with patch("agents.router.OpportunityRouter._stamp_regime", new_callable=AsyncMock):
        await router.route(opp, ActionLevel.NOTIFY)

    router._store.update_status.assert_not_called()


# ---------------------------------------------------------------------------
# static_gate mode — disallowed_regimes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_gate_blocks_disallowed_regime():
    """static_gate rejects when current regime is in disallowed_regimes."""
    opp = _make_opportunity()
    opp.data["regime"] = {
        "trend_regime": "downtrend",
        "volatility_regime": "high",
        "liquidity_regime": "medium",
    }

    agent = _make_agent_with_config(
        regime_policy_mode="static_gate",
        disallowed_regimes={"trend_regime": ["downtrend"]},
    )
    runner = _make_runner_with_agent(agent)
    router = _make_router(runner=runner)

    with patch("agents.router.OpportunityRouter._stamp_regime", new_callable=AsyncMock):
        await router.route(opp, ActionLevel.NOTIFY)

    router._store.update_status.assert_called_once_with(
        opp.id, OpportunityStatus.REJECTED
    )


@pytest.mark.asyncio
async def test_static_gate_blocks_not_in_allowed_regimes():
    """static_gate rejects when current regime is not in allowed_regimes."""
    opp = _make_opportunity()
    opp.data["regime"] = {
        "trend_regime": "uptrend",
        "volatility_regime": "high",
        "liquidity_regime": "medium",
    }

    agent = _make_agent_with_config(
        regime_policy_mode="static_gate",
        allowed_regimes={"volatility_regime": ["low", "medium"]},
    )
    runner = _make_runner_with_agent(agent)
    router = _make_router(runner=runner)

    with patch("agents.router.OpportunityRouter._stamp_regime", new_callable=AsyncMock):
        await router.route(opp, ActionLevel.NOTIFY)

    router._store.update_status.assert_called_once_with(
        opp.id, OpportunityStatus.REJECTED
    )


@pytest.mark.asyncio
async def test_static_gate_allows_compliant_regime():
    """static_gate passes when regime satisfies all allowed/disallowed constraints."""
    opp = _make_opportunity()
    opp.data["regime"] = {
        "trend_regime": "range",
        "volatility_regime": "low",
        "liquidity_regime": "high",
    }

    agent = _make_agent_with_config(
        regime_policy_mode="static_gate",
        allowed_regimes={
            "trend_regime": ["range"],
            "volatility_regime": ["low", "medium"],
        },
        disallowed_regimes={"liquidity_regime": ["low"]},
    )
    runner = _make_runner_with_agent(agent)
    router = _make_router(runner=runner)

    with patch("agents.router.OpportunityRouter._stamp_regime", new_callable=AsyncMock):
        await router.route(opp, ActionLevel.NOTIFY)

    router._store.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_static_gate_no_regime_data_allows():
    """static_gate with no stamped regime data fails open (allows trade)."""
    opp = _make_opportunity()
    # No regime data stamped

    agent = _make_agent_with_config(
        regime_policy_mode="static_gate",
        disallowed_regimes={"trend_regime": ["downtrend"]},
    )
    runner = _make_runner_with_agent(agent)
    router = _make_router(runner=runner)

    with patch("agents.router.OpportunityRouter._stamp_regime", new_callable=AsyncMock):
        await router.route(opp, ActionLevel.NOTIFY)

    router._store.update_status.assert_not_called()


# ---------------------------------------------------------------------------
# rejection includes reason
# ---------------------------------------------------------------------------


def test_check_regime_policy_returns_reason_string():
    """_check_regime_policy must return an explainable reason string."""
    opp = _make_opportunity()
    opp.data["regime"] = {"trend_regime": "uptrend", "volatility_regime": "high"}

    agent = _make_agent_with_config(
        regime_policy_mode="static_gate",
        disallowed_regimes={"volatility_regime": ["high"]},
    )
    runner = _make_runner_with_agent(agent)
    router = _make_router(runner=runner)

    reason = router._check_regime_policy(opp)
    assert reason is not None
    assert "volatility_regime" in reason
    assert "high" in reason


def test_check_regime_policy_none_for_annotate_only():
    opp = _make_opportunity()
    opp.data["regime"] = {"trend_regime": "downtrend"}

    agent = _make_agent_with_config(
        regime_policy_mode="annotate_only",
        disallowed_regimes={"trend_regime": ["downtrend"]},
    )
    runner = _make_runner_with_agent(agent)
    router = _make_router(runner=runner)

    assert router._check_regime_policy(opp) is None


def test_check_regime_policy_none_when_no_runner():
    opp = _make_opportunity()
    opp.data["regime"] = {"trend_regime": "downtrend"}
    router = _make_router()  # no runner
    assert router._check_regime_policy(opp) is None


# ---------------------------------------------------------------------------
# empirical_gate falls back to annotate_only
# ---------------------------------------------------------------------------


def test_empirical_gate_treated_as_annotate_only():
    """empirical_gate is not yet implemented and must behave like annotate_only."""
    opp = _make_opportunity()
    opp.data["regime"] = {"trend_regime": "downtrend"}

    agent = _make_agent_with_config(
        regime_policy_mode="empirical_gate",
        disallowed_regimes={"trend_regime": ["downtrend"]},
    )
    runner = _make_runner_with_agent(agent)
    router = _make_router(runner=runner)

    assert router._check_regime_policy(opp) is None
