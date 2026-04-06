from __future__ import annotations
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock


from agents.models import AgentConfig, ActionLevel, OpportunityStatus
from integrations.bittensor.models import DerivedBittensorView


def _make_config(**overrides) -> AgentConfig:
    params = {
        "symbol": "BTCUSD",
        "timeframe": "5m",
        "max_signal_age_seconds": 600,
        "min_responses_for_opportunity": 3,
        "min_agreement_ratio": 0.65,
        "min_abs_direction": 0.20,
        "min_expected_return": 0.002,
        "max_weighting_divergence": 0.25,
        "use_weighted_view": False,
        "allow_short_signals": True,
    }
    params.update(overrides)
    return AgentConfig(
        name="bittensor_btc_5m",
        strategy="bittensor_signal",
        schedule="continuous",
        action_level=ActionLevel.NOTIFY,
        interval=60,
        parameters=params,
    )


def _make_view(
    direction: float = 0.5,
    expected_return: float = 0.005,
    agreement: float = 0.8,
    responders: int = 5,
    age_seconds: int = 0,
) -> DerivedBittensorView:
    return DerivedBittensorView(
        symbol="BTCUSD",
        timeframe="5m",
        window_id="w1",
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        responder_count=responders,
        bullish_count=3,
        bearish_count=1,
        flat_count=1,
        weighted_direction=direction,
        weighted_expected_return=expected_return,
        agreement_ratio=agreement,
        equal_weight_direction=direction * 0.9,
        equal_weight_expected_return=expected_return * 0.9,
        is_low_confidence=False,
        derivation_version="v1",
    )


def _make_data_bus(view=None):
    source = AsyncMock()
    source.get_latest_signal = AsyncMock(return_value=view)
    bus = MagicMock()
    bus._bittensor_source = source
    return bus


async def test_returns_empty_when_no_source():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    bus = MagicMock(spec=[])
    result = await agent.scan(bus)
    assert result == []


async def test_returns_empty_when_no_view():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    result = await agent.scan(_make_data_bus(view=None))
    assert result == []


async def test_returns_empty_when_stale():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    view = _make_view(age_seconds=700)
    result = await agent.scan(_make_data_bus(view))
    assert result == []


async def test_accepts_timezone_aware_timestamps():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    view = _make_view(direction=0.5, expected_return=0.005, agreement=0.8)
    view = DerivedBittensorView(
        symbol=view.symbol,
        timeframe=view.timeframe,
        window_id=view.window_id,
        timestamp=datetime.now(timezone.utc),
        responder_count=view.responder_count,
        bullish_count=view.bullish_count,
        bearish_count=view.bearish_count,
        flat_count=view.flat_count,
        weighted_direction=view.weighted_direction,
        weighted_expected_return=view.weighted_expected_return,
        agreement_ratio=view.agreement_ratio,
        equal_weight_direction=view.equal_weight_direction,
        equal_weight_expected_return=view.equal_weight_expected_return,
        is_low_confidence=view.is_low_confidence,
        derivation_version=view.derivation_version,
    )
    result = await agent.scan(_make_data_bus(view))
    assert len(result) == 1


async def test_returns_empty_when_low_agreement():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    view = _make_view(agreement=0.4)
    result = await agent.scan(_make_data_bus(view))
    assert result == []


async def test_returns_empty_when_weak_direction():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    view = _make_view(direction=0.1)
    result = await agent.scan(_make_data_bus(view))
    assert result == []


async def test_returns_empty_when_tiny_return():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    view = _make_view(expected_return=0.001)
    result = await agent.scan(_make_data_bus(view))
    assert result == []


async def test_returns_empty_when_too_few_responders():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    view = _make_view(responders=2)
    result = await agent.scan(_make_data_bus(view))
    assert result == []


async def test_emits_buy_opportunity():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    view = _make_view(direction=0.5, expected_return=0.005, agreement=0.8)
    result = await agent.scan(_make_data_bus(view))
    assert len(result) == 1
    opp = result[0]
    assert opp.signal == "BUY"
    assert opp.agent_name == "bittensor_btc_5m"
    assert opp.data["source"] == "bittensor"
    assert opp.data["window_id"] == "w1"
    assert opp.status == OpportunityStatus.PENDING
    assert 0.0 < opp.confidence <= 1.0


async def test_emits_sell_opportunity():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    view = _make_view(direction=-0.5, expected_return=-0.005)
    result = await agent.scan(_make_data_bus(view))
    assert len(result) == 1
    assert result[0].signal == "SELL"


async def test_rejects_short_when_disabled():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config(allow_short_signals=False))
    view = _make_view(direction=-0.5, expected_return=-0.005)
    result = await agent.scan(_make_data_bus(view))
    assert result == []


async def test_uses_equal_weight_by_default():
    from strategies.bittensor_signal import BittensorSignalAgent

    agent = BittensorSignalAgent(_make_config())
    view = _make_view(direction=0.5)
    result = await agent.scan(_make_data_bus(view))
    assert len(result) == 1
    assert "equal_weight_direction" in result[0].data
    assert "weighted_direction" in result[0].data
