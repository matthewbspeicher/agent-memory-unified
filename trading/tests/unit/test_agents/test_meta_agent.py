from datetime import datetime, timedelta, timezone

import pytest

from agents.meta import MetaAgent
from agents.models import AgentConfig, AgentInfo, AgentSignal, AgentStatus, ActionLevel
from data.signal_bus import SignalBus


class FakeRunner:
    def __init__(self, agents: dict[str, AgentConfig]):
        self._agents = agents

    def list_agents(self) -> list[AgentInfo]:
        return [
            AgentInfo(name=n, description="", status=AgentStatus.RUNNING, config=c)
            for n, c in self._agents.items()
        ]

    def get_agent_info(self, name: str) -> AgentInfo | None:
        c = self._agents.get(name)
        if c:
            return AgentInfo(
                name=name, description="", status=AgentStatus.RUNNING, config=c
            )
        return None


def _make_meta(runner, signal_bus=None):
    config = AgentConfig(
        name="meta_agent",
        strategy="meta",
        schedule="continuous",
        action_level=ActionLevel.NOTIFY,
        parameters={
            "boost_delta": 0.05,
            "max_cumulative_boost": 0.15,
            "boost_ttl_minutes": 15,
        },
    )
    return MetaAgent(config=config, runner=runner, signal_bus=signal_bus or SignalBus())


@pytest.mark.asyncio
async def test_meta_agent_applies_bullish_boost():
    agent_config = AgentConfig(
        name="arb_agent",
        strategy="arb",
        schedule="continuous",
        action_level=ActionLevel.AUTO_EXECUTE,
        universe=["AAPL-YES"],
        parameters={"confidence_threshold": 0.7},
    )
    runner = FakeRunner({"arb_agent": agent_config})
    meta = _make_meta(runner)

    signal = AgentSignal(
        source_agent="prediction_market",
        signal_type="volume_anomaly",
        payload={"ticker": "AAPL-YES", "direction": "bullish", "magnitude": 3.0},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    await meta.handle_signal(signal)

    assert agent_config.runtime_overrides.get("confidence_threshold") == 0.65


@pytest.mark.asyncio
async def test_meta_agent_applies_bearish_boost():
    agent_config = AgentConfig(
        name="arb_agent",
        strategy="arb",
        schedule="continuous",
        action_level=ActionLevel.AUTO_EXECUTE,
        universe=["AAPL-YES"],
        parameters={"confidence_threshold": 0.7},
    )
    runner = FakeRunner({"arb_agent": agent_config})
    meta = _make_meta(runner)

    signal = AgentSignal(
        source_agent="prediction_market",
        signal_type="volume_anomaly",
        payload={"ticker": "AAPL-YES", "direction": "bearish", "magnitude": 2.5},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    await meta.handle_signal(signal)

    assert agent_config.runtime_overrides.get("confidence_threshold") == 0.75


@pytest.mark.asyncio
async def test_meta_agent_respects_max_cumulative_boost():
    agent_config = AgentConfig(
        name="arb_agent",
        strategy="arb",
        schedule="continuous",
        action_level=ActionLevel.AUTO_EXECUTE,
        universe=["AAPL-YES"],
        parameters={"confidence_threshold": 0.7},
    )
    runner = FakeRunner({"arb_agent": agent_config})
    meta = _make_meta(runner)

    now = datetime.now(timezone.utc)
    for i in range(5):
        signal = AgentSignal(
            source_agent="prediction_market",
            signal_type="volume_anomaly",
            payload={"ticker": "AAPL-YES", "direction": "bullish", "magnitude": 3.0},
            expires_at=now + timedelta(minutes=15),
        )
        await meta.handle_signal(signal)

    threshold = agent_config.runtime_overrides.get("confidence_threshold")
    assert threshold == 0.55  # 0.7 - 0.15 max cumulative


@pytest.mark.asyncio
async def test_meta_agent_decays_expired_boosts():
    agent_config = AgentConfig(
        name="arb_agent",
        strategy="arb",
        schedule="continuous",
        action_level=ActionLevel.AUTO_EXECUTE,
        universe=["AAPL-YES"],
        parameters={"confidence_threshold": 0.7},
    )
    runner = FakeRunner({"arb_agent": agent_config})
    meta = _make_meta(runner)

    signal = AgentSignal(
        source_agent="prediction_market",
        signal_type="volume_anomaly",
        payload={"ticker": "AAPL-YES", "direction": "bullish", "magnitude": 3.0},
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # already expired
    )
    await meta.handle_signal(signal)
    assert agent_config.runtime_overrides.get("confidence_threshold") == 0.65

    meta.decay_expired_boosts()
    assert agent_config.runtime_overrides.get("confidence_threshold", 0.7) == 0.7


@pytest.mark.asyncio
async def test_meta_agent_caches_signals_for_annotation():
    runner = FakeRunner({})
    meta = _make_meta(runner)

    signal = AgentSignal(
        source_agent="prediction_market",
        signal_type="volume_anomaly",
        payload={"ticker": "AAPL-YES", "direction": "bullish", "magnitude": 3.0},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    await meta.handle_signal(signal)

    cached = meta.get_signals_for_ticker("AAPL-YES")
    assert len(cached) == 1
    assert cached[0].signal_type == "volume_anomaly"


@pytest.mark.asyncio
async def test_meta_agent_ignores_agents_without_matching_universe():
    agent_config = AgentConfig(
        name="bond_agent",
        strategy="bonds",
        schedule="continuous",
        action_level=ActionLevel.AUTO_EXECUTE,
        universe=["BOND-YES"],
        parameters={"confidence_threshold": 0.7},
    )
    runner = FakeRunner({"bond_agent": agent_config})
    meta = _make_meta(runner)

    signal = AgentSignal(
        source_agent="prediction_market",
        signal_type="volume_anomaly",
        payload={"ticker": "AAPL-YES", "direction": "bullish", "magnitude": 3.0},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    await meta.handle_signal(signal)

    assert "confidence_threshold" not in agent_config.runtime_overrides
