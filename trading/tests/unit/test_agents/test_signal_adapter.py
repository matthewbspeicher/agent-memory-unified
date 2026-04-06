from datetime import datetime, timedelta, timezone

import pytest

from agents.models import AgentSignal
from agents.signal_adapter import SignalAdapter, SignalAdapterRunner
from data.signal_bus import SignalBus


class FakeAdapter(SignalAdapter):
    def __init__(self, signals_to_return: list[AgentSignal]):
        self._signals = signals_to_return
        self.poll_count = 0

    def source_name(self) -> str:
        return "fake"

    async def poll(self) -> list[AgentSignal]:
        self.poll_count += 1
        return self._signals


class ErrorAdapter(SignalAdapter):
    def source_name(self) -> str:
        return "error_source"

    async def poll(self) -> list[AgentSignal]:
        raise RuntimeError("adapter exploded")


@pytest.mark.asyncio
async def test_adapter_runner_publishes_signals():
    now = datetime.now(timezone.utc)
    signal = AgentSignal(
        source_agent="fake",
        signal_type="test_signal",
        payload={"value": 42},
        expires_at=now + timedelta(minutes=5),
    )
    adapter = FakeAdapter([signal])
    bus = SignalBus()
    runner = SignalAdapterRunner(adapters=[adapter], signal_bus=bus)

    await runner.poll_once("fake")

    assert adapter.poll_count == 1
    results = bus.query(signal_type="test_signal")
    assert len(results) == 1
    assert results[0].payload["value"] == 42


@pytest.mark.asyncio
async def test_adapter_runner_survives_error():
    adapter = ErrorAdapter()
    bus = SignalBus()
    runner = SignalAdapterRunner(adapters=[adapter], signal_bus=bus)

    await runner.poll_once("error_source")
    assert len(bus.query()) == 0


@pytest.mark.asyncio
async def test_adapter_runner_ignores_unknown_name():
    bus = SignalBus()
    runner = SignalAdapterRunner(adapters=[], signal_bus=bus)
    await runner.poll_once("nonexistent")


from unittest.mock import AsyncMock, MagicMock
from agents.adapters.prediction_market import PredictionMarketAdapter


@pytest.mark.asyncio
async def test_prediction_market_adapter_detects_volume_spike():
    mock_data_bus = MagicMock()
    mock_data_bus.get_kalshi_markets = AsyncMock(
        return_value=[
            {"ticker": "AAPL-YES", "volume": 3000, "avg_volume": 1000, "yes_ask": 0.55},
        ]
    )
    adapter = PredictionMarketAdapter(
        data_bus=mock_data_bus, volume_spike_threshold=2.0, price_move_threshold=0.10
    )

    signals = await adapter.poll()
    assert len(signals) == 1
    assert signals[0].signal_type == "volume_anomaly"
    assert signals[0].payload["ticker"] == "AAPL-YES"
    assert signals[0].payload["magnitude"] == 3.0


@pytest.mark.asyncio
async def test_prediction_market_adapter_ignores_normal_volume():
    mock_data_bus = MagicMock()
    mock_data_bus.get_kalshi_markets = AsyncMock(
        return_value=[
            {"ticker": "AAPL-YES", "volume": 1200, "avg_volume": 1000, "yes_ask": 0.55},
        ]
    )
    adapter = PredictionMarketAdapter(
        data_bus=mock_data_bus, volume_spike_threshold=2.0, price_move_threshold=0.10
    )

    signals = await adapter.poll()
    assert len(signals) == 0


@pytest.mark.asyncio
async def test_prediction_market_adapter_survives_missing_data():
    mock_data_bus = MagicMock()
    mock_data_bus.get_kalshi_markets = AsyncMock(return_value=[])
    adapter = PredictionMarketAdapter(data_bus=mock_data_bus)

    signals = await adapter.poll()
    assert signals == []
