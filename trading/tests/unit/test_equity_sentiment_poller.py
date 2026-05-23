"""Tests for the equity sentiment background poller (ADR-0011 follow-up).

Closes the gap from ADR-0011's "negative consequence" — equity personas
(Buffett/Graham/Lynch/etc.) couldn't see sentiment because the topic only
fired off bittensor_consensus (BTC/ETH).  The poller in
``IntelligenceLayer.start()`` drives the topic on a configured equity
universe so those personas' ``consume_sentiment: true`` opt-ins finally
get data.

Covers:
1. _should_run_equity_poller respects enabled + non-empty universe.
2. Empty universe → no task started.
3. Disabled intel → no task started even if universe is set.
4. Loop publishes intel_sentiment per symbol on each cycle.
5. Per-symbol failures degrade gracefully (don't kill the loop).
6. stop() cancels the task cleanly.
7. get_status() surfaces the new metrics.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from data.signal_bus import SignalBus
from intelligence.layer import IntelligenceLayer
from intelligence.models import IntelReport


@dataclass
class _FakeConfig:
    """Stub matching the IntelligenceConfig surface used by the layer."""

    enabled: bool = True
    coinglass_api_key: str | None = None
    lunarcrush_api_key: str | None = None
    circuit_breaker_failures: int = 3
    circuit_breaker_reset_seconds: int = 60
    timeout_ms: int = 5000
    max_adjustment_pct: float = 0.5
    weights: dict = field(default_factory=dict)
    risk_var_threshold_pct: float = 0.05
    risk_horizon_days: int = 1

    # New equity poller knobs (mirror IntelligenceConfig)
    equity_sentiment_universe: list = field(default_factory=list)
    equity_sentiment_interval_seconds: int = 900
    equity_sentiment_max_concurrency: int = 3

    def __post_init__(self):
        if not self.weights:
            self.weights = {
                "on_chain": 0.2,
                "sentiment": 0.15,
                "anomaly": 0.1,
                "order_flow": 0.1,
                "regime": 0.15,
                "risk_audit": 0.1,
                "derivatives": 0.1,
                "knowledge_graph": 0.1,
            }


def _report(symbol: str, score: float = 0.3) -> IntelReport:
    return IntelReport(
        source="sentiment",
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        score=score,
        confidence=0.7,
        veto=False,
        details={"fear_greed_value": 40},
    )


# ---------------------------------------------------------------------------
# 1-3. _should_run_equity_poller + start gating
# ---------------------------------------------------------------------------


class TestShouldRunGating:
    def test_disabled_layer_does_not_run(self):
        cfg = _FakeConfig(
            enabled=False, equity_sentiment_universe=["AAPL", "MSFT"]
        )
        layer = IntelligenceLayer(signal_bus=SignalBus(), config=cfg)
        assert layer._should_run_equity_poller() is False

    def test_empty_universe_does_not_run(self):
        cfg = _FakeConfig(enabled=True, equity_sentiment_universe=[])
        layer = IntelligenceLayer(signal_bus=SignalBus(), config=cfg)
        assert layer._should_run_equity_poller() is False

    def test_zero_interval_does_not_run(self):
        cfg = _FakeConfig(
            enabled=True,
            equity_sentiment_universe=["AAPL"],
            equity_sentiment_interval_seconds=0,
        )
        layer = IntelligenceLayer(signal_bus=SignalBus(), config=cfg)
        assert layer._should_run_equity_poller() is False

    def test_happy_config_runs(self):
        cfg = _FakeConfig(
            enabled=True,
            equity_sentiment_universe=["AAPL", "MSFT"],
            equity_sentiment_interval_seconds=900,
        )
        layer = IntelligenceLayer(signal_bus=SignalBus(), config=cfg)
        assert layer._should_run_equity_poller() is True

    @pytest.mark.asyncio
    async def test_start_creates_task_when_configured(self):
        cfg = _FakeConfig(
            enabled=True,
            equity_sentiment_universe=["AAPL"],
            equity_sentiment_interval_seconds=900,
        )
        layer = IntelligenceLayer(signal_bus=SignalBus(), config=cfg)
        # Replace sentiment provider with a no-op so the loop doesn't hit the network.
        layer._sentiment.analyze = _make_async(_report("AAPL"))
        await layer.start()
        try:
            assert layer._equity_sentiment_task is not None
            assert not layer._equity_sentiment_task.done()
        finally:
            await layer.stop()

    @pytest.mark.asyncio
    async def test_start_skips_task_when_universe_empty(self):
        cfg = _FakeConfig(enabled=True, equity_sentiment_universe=[])
        layer = IntelligenceLayer(signal_bus=SignalBus(), config=cfg)
        await layer.start()
        try:
            assert layer._equity_sentiment_task is None
        finally:
            await layer.stop()


# ---------------------------------------------------------------------------
# 4-5. Loop behaviour
# ---------------------------------------------------------------------------


def _make_async(value):
    """Return an async fn that always returns *value* (or raises if Exception)."""

    async def _fn(*_args, **_kwargs):
        if isinstance(value, Exception):
            raise value
        return value

    return _fn


def _make_async_per_symbol(results: dict):
    """Returns an async fn that looks up the symbol and yields the mapped value."""

    async def _fn(symbol):
        v = results.get(symbol)
        if isinstance(v, Exception):
            raise v
        return v

    return _fn


class TestPollerLoopBehaviour:
    @pytest.mark.asyncio
    async def test_publishes_per_symbol_on_first_cycle(self):
        bus = SignalBus()
        cfg = _FakeConfig(
            enabled=True,
            equity_sentiment_universe=["AAPL", "MSFT", "GOOGL"],
            equity_sentiment_interval_seconds=30,
        )
        layer = IntelligenceLayer(signal_bus=bus, config=cfg)
        layer._sentiment.analyze = _make_async_per_symbol(
            {
                "AAPL": _report("AAPL", 0.3),
                "MSFT": _report("MSFT", 0.5),
                "GOOGL": _report("GOOGL", -0.2),
            }
        )
        await layer.start()
        try:
            # Give the loop one tick to run its first iteration.
            await asyncio.sleep(0.05)
            signals = bus.query(signal_type="intel_sentiment")
            symbols = {s.payload["symbol"] for s in signals}
            assert symbols == {"AAPL", "MSFT", "GOOGL"}
            assert layer._equity_sentiment_polls >= 3
            assert layer._equity_sentiment_published == 3
        finally:
            await layer.stop()

    @pytest.mark.asyncio
    async def test_per_symbol_failure_does_not_kill_loop(self):
        bus = SignalBus()
        cfg = _FakeConfig(
            enabled=True,
            equity_sentiment_universe=["AAPL", "MSFT"],
            equity_sentiment_interval_seconds=30,
        )
        layer = IntelligenceLayer(signal_bus=bus, config=cfg)
        layer._sentiment.analyze = _make_async_per_symbol(
            {
                "AAPL": RuntimeError("provider down"),
                "MSFT": _report("MSFT", 0.4),
            }
        )
        await layer.start()
        try:
            await asyncio.sleep(0.05)
            signals = bus.query(signal_type="intel_sentiment")
            symbols = {s.payload["symbol"] for s in signals}
            # AAPL failed, MSFT still published
            assert symbols == {"MSFT"}
            assert layer._provider_failures >= 1
            # Loop must still be alive
            assert not layer._equity_sentiment_task.done()
        finally:
            await layer.stop()

    @pytest.mark.asyncio
    async def test_none_report_does_not_publish(self):
        bus = SignalBus()
        cfg = _FakeConfig(
            enabled=True,
            equity_sentiment_universe=["AAPL"],
            equity_sentiment_interval_seconds=30,
        )
        layer = IntelligenceLayer(signal_bus=bus, config=cfg)
        layer._sentiment.analyze = _make_async(None)
        await layer.start()
        try:
            await asyncio.sleep(0.05)
            assert bus.query(signal_type="intel_sentiment") == []
            assert layer._equity_sentiment_published == 0
        finally:
            await layer.stop()


# ---------------------------------------------------------------------------
# 6. Cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    @pytest.mark.asyncio
    async def test_stop_cancels_the_task(self):
        cfg = _FakeConfig(
            enabled=True,
            equity_sentiment_universe=["AAPL"],
            equity_sentiment_interval_seconds=3600,  # long sleep so we can verify cancel
        )
        layer = IntelligenceLayer(signal_bus=SignalBus(), config=cfg)
        layer._sentiment.analyze = _make_async(_report("AAPL"))
        await layer.start()
        task = layer._equity_sentiment_task
        assert task is not None
        await layer.stop()
        assert task.done() or task.cancelled()
        # Idempotent
        await layer.stop()


# ---------------------------------------------------------------------------
# 7. Status exposure
# ---------------------------------------------------------------------------


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_includes_equity_sentiment_block(self):
        cfg = _FakeConfig(
            enabled=True,
            equity_sentiment_universe=["AAPL", "MSFT"],
            equity_sentiment_interval_seconds=900,
        )
        layer = IntelligenceLayer(signal_bus=SignalBus(), config=cfg)
        status = layer.get_status()
        assert "equity_sentiment" in status
        eq = status["equity_sentiment"]
        assert eq["universe_size"] == 2
        assert eq["interval_seconds"] == 900
        assert eq["polls_total"] == 0
        assert eq["published_total"] == 0
        # Not started yet, so running is False
        assert eq["running"] is False
        assert eq["enabled"] is True

    def test_status_when_disabled(self):
        cfg = _FakeConfig(enabled=False, equity_sentiment_universe=["AAPL"])
        layer = IntelligenceLayer(signal_bus=SignalBus(), config=cfg)
        eq = layer.get_status()["equity_sentiment"]
        assert eq["enabled"] is False
        assert eq["running"] is False
