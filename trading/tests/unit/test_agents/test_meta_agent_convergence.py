"""Tests for the meta_agent consumer of the agent_convergence topic (G2 of
the May-2026 plan; closes the ADR-0013 loop).

A strong convergence (≥ N agents, ≥ M avg_confidence) should trigger a
larger-than-default boost on agents whose universe contains the symbol.
A weak convergence should be ignored.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.meta import MetaAgent
from agents.models import (
    ActionLevel,
    AgentConfig,
    AgentInfo,
    AgentSignal,
    AgentStatus,
)
from data.signal_bus import SignalBus


class _FakeRunner:
    def __init__(self, agents: dict[str, AgentConfig]):
        self._agents = agents

    def list_agents(self) -> list[AgentInfo]:
        return [
            AgentInfo(name=n, description="", status=AgentStatus.RUNNING, config=c)
            for n, c in self._agents.items()
        ]

    def get_agent_info(self, name: str) -> AgentInfo | None:
        c = self._agents.get(name)
        return (
            AgentInfo(name=name, description="", status=AgentStatus.RUNNING, config=c)
            if c
            else None
        )


def _meta(runner, **overrides):
    params = {
        "boost_delta": 0.05,
        "max_cumulative_boost": 0.15,
        "boost_ttl_minutes": 15,
        "convergence_min_agents": 3,
        "convergence_min_confidence": 0.65,
        "convergence_boost_mult_base": 1.5,
    }
    params.update(overrides)
    config = AgentConfig(
        name="meta_agent",
        strategy="meta",
        schedule="continuous",
        action_level=ActionLevel.NOTIFY,
        parameters=params,
    )
    return MetaAgent(config=config, runner=runner, signal_bus=SignalBus())


def _convergence_signal(
    *,
    symbol: str = "AAPL",
    direction: str = "BUY",
    agents: list[str] | None = None,
    avg_confidence: float = 0.75,
    ttl_minutes: int = 15,
) -> AgentSignal:
    return AgentSignal(
        source_agent="warroom_engine",
        signal_type="agent_convergence",
        payload={
            "convergence_id": "abc",
            "symbol": symbol,
            "direction": direction,
            "agents": agents or ["buffett_value", "lynch_growth", "marks_macro"],
            "opportunity_ids": ["o1", "o2", "o3"],
            "avg_confidence": avg_confidence,
            "first_seen": "2026-05-22T14:00:00+00:00",
            "synthesis": "",
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )


def _target_agent(universe: list[str], baseline: float = 0.7) -> AgentConfig:
    return AgentConfig(
        name="target_agent",
        strategy="rsi",
        schedule="continuous",
        action_level=ActionLevel.NOTIFY,
        universe=universe,
        parameters={"confidence_threshold": baseline},
    )


# ---------------------------------------------------------------------------
# Happy path: strong BUY convergence → bullish boost (lowers threshold)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strong_convergence_lowers_threshold():
    target = _target_agent(["AAPL"])
    runner = _FakeRunner({"target_agent": target})
    meta = _meta(runner)

    sig = _convergence_signal(
        symbol="AAPL",
        direction="BUY",
        agents=["buffett_value", "lynch_growth", "marks_macro"],
        avg_confidence=0.75,
    )
    await meta.handle_signal(sig)

    # Bullish boost is negative delta on threshold (easier to fire).
    new = target.runtime_overrides.get("confidence_threshold")
    assert new is not None
    assert new < 0.7, "bullish convergence should lower threshold"


@pytest.mark.asyncio
async def test_strong_convergence_sell_raises_threshold():
    target = _target_agent(["MSFT"])
    runner = _FakeRunner({"target_agent": target})
    meta = _meta(runner)

    sig = _convergence_signal(
        symbol="MSFT",
        direction="SELL",
        agents=["buffett_value", "graham_deep_value", "klarman_distressed"],
        avg_confidence=0.7,
    )
    await meta.handle_signal(sig)

    new = target.runtime_overrides.get("confidence_threshold")
    assert new is not None
    assert new > 0.7, "bearish convergence should raise threshold"


# ---------------------------------------------------------------------------
# Quality gates: too few agents / too low confidence → no boost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_below_min_agents_is_ignored():
    target = _target_agent(["AAPL"])
    runner = _FakeRunner({"target_agent": target})
    meta = _meta(runner, convergence_min_agents=4)  # raise the bar

    sig = _convergence_signal(
        symbol="AAPL",
        agents=["a1", "a2", "a3"],  # only 3, below the 4 floor
        avg_confidence=0.9,
    )
    await meta.handle_signal(sig)

    assert "confidence_threshold" not in target.runtime_overrides


@pytest.mark.asyncio
async def test_below_min_confidence_is_ignored():
    target = _target_agent(["AAPL"])
    runner = _FakeRunner({"target_agent": target})
    meta = _meta(runner)  # default min_confidence=0.65

    sig = _convergence_signal(
        symbol="AAPL",
        agents=["a1", "a2", "a3", "a4"],
        avg_confidence=0.50,  # below floor
    )
    await meta.handle_signal(sig)

    assert "confidence_threshold" not in target.runtime_overrides


@pytest.mark.asyncio
async def test_unknown_direction_is_ignored():
    target = _target_agent(["AAPL"])
    runner = _FakeRunner({"target_agent": target})
    meta = _meta(runner)

    sig = AgentSignal(
        source_agent="warroom_engine",
        signal_type="agent_convergence",
        payload={
            "convergence_id": "x",
            "symbol": "AAPL",
            "direction": "HOLD",  # not BUY/SELL — should be skipped
            "agents": ["a1", "a2", "a3"],
            "opportunity_ids": [],
            "avg_confidence": 0.8,
            "first_seen": "x",
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    await meta.handle_signal(sig)

    assert "confidence_threshold" not in target.runtime_overrides


# ---------------------------------------------------------------------------
# Scaling: more agents + higher confidence → bigger boost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_more_agents_yields_larger_boost():
    target_small = _target_agent(["AAPL"])
    target_large = _target_agent(["AAPL"])

    # Two separate metas, each with one target — easier to isolate boost size.
    meta_small = _meta(_FakeRunner({"target": target_small}))
    meta_large = _meta(_FakeRunner({"target": target_large}))

    sig_small = _convergence_signal(
        symbol="AAPL",
        agents=["a1", "a2", "a3"],  # exactly at floor
        avg_confidence=0.70,
    )
    sig_large = _convergence_signal(
        symbol="AAPL",
        agents=["a1", "a2", "a3", "a4", "a5", "a6"],  # 3 above floor
        avg_confidence=0.70,
    )

    await meta_small.handle_signal(sig_small)
    await meta_large.handle_signal(sig_large)

    delta_small = 0.7 - target_small.runtime_overrides["confidence_threshold"]
    delta_large = 0.7 - target_large.runtime_overrides["confidence_threshold"]
    assert delta_large > delta_small, "more agents should produce larger boost"


@pytest.mark.asyncio
async def test_higher_confidence_yields_larger_boost():
    target_low = _target_agent(["AAPL"])
    target_high = _target_agent(["AAPL"])

    meta_low = _meta(_FakeRunner({"target": target_low}))
    meta_high = _meta(_FakeRunner({"target": target_high}))

    sig_low = _convergence_signal(
        symbol="AAPL",
        agents=["a1", "a2", "a3"],
        avg_confidence=0.66,  # just above floor
    )
    sig_high = _convergence_signal(
        symbol="AAPL",
        agents=["a1", "a2", "a3"],
        avg_confidence=0.95,
    )

    await meta_low.handle_signal(sig_low)
    await meta_high.handle_signal(sig_high)

    delta_low = 0.7 - target_low.runtime_overrides["confidence_threshold"]
    delta_high = 0.7 - target_high.runtime_overrides["confidence_threshold"]
    assert delta_high > delta_low, "higher avg_confidence should produce larger boost"


# ---------------------------------------------------------------------------
# Universe targeting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_affects_agents_in_universe():
    aapl_agent = _target_agent(["AAPL"])
    msft_agent = _target_agent(["MSFT"])
    runner = _FakeRunner(
        {"aapl_agent": aapl_agent, "msft_agent": msft_agent}
    )
    meta = _meta(runner)

    await meta.handle_signal(_convergence_signal(symbol="AAPL"))

    assert "confidence_threshold" in aapl_agent.runtime_overrides
    assert "confidence_threshold" not in msft_agent.runtime_overrides
