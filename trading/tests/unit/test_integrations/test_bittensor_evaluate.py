from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from integrations.bittensor.models import (
    BittensorEvaluationWindow,
    RawMinerForecast,
)


def _make_forecast(hotkey: str, predictions: list[float]) -> RawMinerForecast:
    return RawMinerForecast(
        window_id="w1", request_uuid="req1",
        collected_at=datetime(2026, 3, 28, 12, 0),
        miner_uid=1, miner_hotkey=hotkey,
        stream_id="BTCUSD-5m", topic_id=1, schema_id=1,
        symbol="BTCUSD", timeframe="5m",
        feature_ids=[1, 2, 3, 4, 5], prediction_size=5,
        predictions=predictions, hashed_predictions=None,
        hash_verified=True, incentive_score=0.5,
    )


async def test_evaluate_window_scores_miners():
    from integrations.bittensor.evaluator import BittensorEvaluator

    forecasts = [
        _make_forecast("hk1", [100, 101, 102, 103, 104]),
        _make_forecast("hk2", [100, 99, 98, 97, 96]),
    ]
    realized_closes = [100.0, 100.5, 101.0, 101.5, 102.0]

    mock_store = MagicMock()
    mock_store.get_raw_forecasts_by_window = AsyncMock(return_value=forecasts)
    mock_store.save_realized_window = AsyncMock()
    mock_store.save_accuracy_records = AsyncMock()
    mock_store.update_miner_ranking = AsyncMock()
    mock_store.get_accuracy_rollup = AsyncMock(return_value={})
    mock_store.mark_window_evaluated = AsyncMock()

    mock_coingecko = MagicMock()
    mock_coingecko.get_ohlc_closes = AsyncMock(return_value=realized_closes)

    mock_event_bus = MagicMock()
    mock_event_bus.publish = AsyncMock()

    evaluator = BittensorEvaluator(
        store=mock_store,
        data_bus=MagicMock(),
        event_bus=mock_event_bus,
        coingecko=mock_coingecko,
    )

    window = BittensorEvaluationWindow(
        window_id="w1", symbol="BTCUSD", timeframe="5m",
        collected_at=datetime(2026, 3, 28, 12, 0), prediction_size=5,
    )

    await evaluator._evaluate_window(window)

    mock_store.save_realized_window.assert_called_once()
    mock_store.save_accuracy_records.assert_called_once()
    records = mock_store.save_accuracy_records.call_args[0][0]
    assert len(records) == 2

    hk1_record = [r for r in records if r.miner_hotkey == "hk1"][0]
    assert hk1_record.direction_correct is True

    hk2_record = [r for r in records if r.miner_hotkey == "hk2"][0]
    assert hk2_record.direction_correct is False


async def test_evaluate_window_skips_insufficient_candles():
    from integrations.bittensor.evaluator import BittensorEvaluator

    mock_store = MagicMock()
    mock_store.get_raw_forecasts_by_window = AsyncMock(return_value=[
        _make_forecast("hk1", [100, 101, 102, 103, 104]),
    ])
    mock_store.save_realized_window = AsyncMock()
    mock_store.save_accuracy_records = AsyncMock()

    mock_coingecko = MagicMock()
    mock_coingecko.get_ohlc_closes = AsyncMock(return_value=[100.0, 101.0])

    evaluator = BittensorEvaluator(
        store=mock_store, data_bus=MagicMock(), event_bus=MagicMock(),
        coingecko=mock_coingecko,
    )

    window = BittensorEvaluationWindow(
        window_id="w1", symbol="BTCUSD", timeframe="5m",
        collected_at=datetime(2026, 3, 28, 12, 0), prediction_size=5,
    )
    await evaluator._evaluate_window(window)

    mock_store.save_realized_window.assert_not_called()
    mock_store.save_accuracy_records.assert_not_called()


async def test_evaluate_window_updates_counters():
    from integrations.bittensor.evaluator import BittensorEvaluator

    mock_store = MagicMock()
    mock_store.get_raw_forecasts_by_window = AsyncMock(return_value=[
        _make_forecast("hk1", [100, 101, 102, 103, 104]),
    ])
    mock_store.save_realized_window = AsyncMock()
    mock_store.save_accuracy_records = AsyncMock()
    mock_store.update_miner_ranking = AsyncMock()
    mock_store.get_accuracy_rollup = AsyncMock(return_value={})
    mock_store.mark_window_evaluated = AsyncMock()

    mock_coingecko = MagicMock()
    mock_coingecko.get_ohlc_closes = AsyncMock(return_value=[100, 101, 102, 103, 104])

    mock_event_bus = MagicMock()
    mock_event_bus.publish = AsyncMock()

    evaluator = BittensorEvaluator(
        store=mock_store, data_bus=MagicMock(), event_bus=mock_event_bus,
        coingecko=mock_coingecko,
    )

    window = BittensorEvaluationWindow(
        window_id="w1", symbol="BTCUSD", timeframe="5m",
        collected_at=datetime(2026, 3, 28, 12, 0), prediction_size=5,
    )
    await evaluator._evaluate_window(window)

    assert evaluator.windows_evaluated_total == 1
    assert evaluator.last_success_at is not None


async def test_evaluate_window_skips_unknown_symbol():
    from integrations.bittensor.evaluator import BittensorEvaluator

    evaluator = BittensorEvaluator(
        store=MagicMock(), data_bus=MagicMock(), event_bus=MagicMock(),
        coingecko=None,
    )

    window = BittensorEvaluationWindow(
        window_id="w1", symbol="UNKNOWN", timeframe="5m",
        collected_at=datetime(2026, 3, 28, 12, 0), prediction_size=5,
    )
    await evaluator._evaluate_window(window)
