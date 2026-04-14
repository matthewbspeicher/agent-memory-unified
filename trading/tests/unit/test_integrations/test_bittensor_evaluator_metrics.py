"""Tests for MinerEvaluator metrics instrumentation on skip paths."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from integrations.bittensor.evaluator import MinerEvaluator
from integrations.bittensor.models import BittensorEvaluationWindow, BittensorMetrics


@pytest.fixture
def evaluator():
    store = MagicMock()
    store.save_realized_window = AsyncMock()
    store.get_raw_forecasts_by_window = AsyncMock(return_value=[])

    data_bus = MagicMock()
    metrics = BittensorMetrics()

    return MinerEvaluator(store=store, data_bus=data_bus, metrics=metrics), metrics


@pytest.fixture
def window():
    return BittensorEvaluationWindow(
        window_id="win-1",
        symbol="BTCUSD",
        timeframe="5m",
        collected_at=datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc),
        prediction_size=12,
    )


@pytest.mark.asyncio
async def test_skip_no_bar_data_sets_metrics(evaluator, window):
    evaluator_obj, metrics = evaluator
    evaluator_obj.data_bus.get_historical = AsyncMock(return_value=[])

    await evaluator_obj._evaluate_window(window)

    assert metrics.windows_skipped == 1
    assert metrics.last_skip_reason == "no_bar_data"


@pytest.mark.asyncio
async def test_skip_insufficient_bars_sets_metrics(evaluator, window):
    evaluator_obj, metrics = evaluator
    # Bars exist but not enough of them past collected_at
    bar = MagicMock()
    bar.timestamp = window.collected_at
    bar.close = 100.0
    bar.open = 100.0
    evaluator_obj.data_bus.get_historical = AsyncMock(return_value=[bar, bar])

    await evaluator_obj._evaluate_window(window)

    assert metrics.windows_skipped == 1
    assert metrics.last_skip_reason == "insufficient_bars"


def test_evaluator_accepts_metrics_param():
    """MinerEvaluator accepts an optional metrics parameter."""
    metrics = BittensorMetrics()
    ev = MinerEvaluator(store=MagicMock(), data_bus=MagicMock(), metrics=metrics)
    assert ev.metrics is metrics


def test_evaluator_creates_default_metrics_when_omitted():
    """Backward compat: if no metrics provided, evaluator creates its own."""
    ev = MinerEvaluator(store=MagicMock(), data_bus=MagicMock())
    assert isinstance(ev.metrics, BittensorMetrics)
