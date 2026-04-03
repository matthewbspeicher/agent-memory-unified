from __future__ import annotations

import pytest

from integrations.bittensor.evaluator import compute_direction_correct, compute_magnitude_error, compute_path_correlation


def test_direction_correct_bullish_match():
    predicted = [0.1, 0.2, 0.3, 0.4, 0.5]
    actual = [0.05, 0.1, 0.15, 0.2, 0.25]
    assert compute_direction_correct(predicted, actual) is True


def test_direction_correct_mismatch():
    predicted = [0.1, 0.2, 0.3, 0.4, 0.5]
    actual = [-0.1, -0.2, -0.3, -0.4, -0.5]
    assert compute_direction_correct(predicted, actual) is False


def test_direction_correct_empty():
    assert compute_direction_correct([], []) is False


def test_magnitude_error():
    error = compute_magnitude_error(0.05, 0.03)
    assert abs(error - 0.02) < 1e-9


def test_path_correlation_perfect():
    predicted = [1.0, 2.0, 3.0, 4.0, 5.0]
    actual = [2.0, 4.0, 6.0, 8.0, 10.0]
    corr = compute_path_correlation(predicted, actual)
    assert corr is not None
    assert abs(corr - 1.0) < 1e-9


def test_path_correlation_too_short():
    assert compute_path_correlation([1.0], [2.0]) is None


from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from integrations.bittensor.evaluator import BittensorEvaluator
from integrations.bittensor.models import (
    BittensorEvaluationWindow, RawMinerForecast,
)


def _make_evaluator(*, coingecko=None, adapter=None, store=None, event_bus=None):
    return BittensorEvaluator(
        store=store or AsyncMock(),
        data_bus=MagicMock(),
        event_bus=event_bus or AsyncMock(),
        coingecko=coingecko,
        adapter=adapter,
    )


class TestEvaluatorOrchestration:
    async def test_evaluate_window_calls_ranking_pipeline(self):
        store = AsyncMock()
        store.get_raw_forecasts_by_window = AsyncMock(return_value=[
            RawMinerForecast(
                window_id="w1", request_uuid="r1",
                collected_at=datetime(2026, 3, 31),
                miner_uid=1, miner_hotkey="5Fhot1",
                stream_id="BTCUSD-5m", topic_id=1, schema_id=1,
                symbol="BTCUSD", timeframe="5m",
                feature_ids=[1, 2, 3, 4, 5], prediction_size=100,
                predictions=[1.0 + i * 0.01 for i in range(100)],
                hashed_predictions=None, hash_verified=True,
                incentive_score=0.5,
            ),
        ])
        store.save_accuracy_records = AsyncMock()
        store.save_realized_window = AsyncMock()
        store.update_miner_ranking = AsyncMock()
        store.mark_window_evaluated = AsyncMock()
        store.get_accuracy_rollup = AsyncMock(return_value={
            "5Fhot1": {
                "windows_evaluated": 50,
                "direction_accuracy": 0.7,
                "mean_magnitude_error": 0.03,
                "mean_path_correlation": 0.5,
            },
        })

        adapter = MagicMock()
        adapter.get_incentive_scores = MagicMock(return_value={"5Fhot1": 0.5})

        cg = AsyncMock()
        cg.get_ohlc_closes = AsyncMock(return_value=[1.0 + i * 0.005 for i in range(100)])

        evaluator = _make_evaluator(coingecko=cg, adapter=adapter, store=store)

        window = BittensorEvaluationWindow(
            window_id="w1", symbol="BTCUSD", timeframe="5m",
            collected_at=datetime(2026, 3, 31), prediction_size=100,
        )
        await evaluator._evaluate_window(window)

        store.save_accuracy_records.assert_awaited_once()
        store.update_miner_ranking.assert_awaited_once()
        store.mark_window_evaluated.assert_awaited_once_with("w1")
        adapter.get_incentive_scores.assert_called_once()


class TestEvaluatorExpiry:
    async def test_expire_stale_windows_called(self):
        store = AsyncMock()
        store.get_unevaluated_windows = AsyncMock(return_value=[])
        store.expire_stale_windows = AsyncMock(return_value=0)

        evaluator = _make_evaluator(store=store)
        await evaluator._evaluate_mature_windows()

        store.expire_stale_windows.assert_awaited_once()
