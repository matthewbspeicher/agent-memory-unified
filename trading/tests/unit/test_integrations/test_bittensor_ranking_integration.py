"""Integration test: evaluator → ranking → store pipeline."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from integrations.bittensor.evaluator import BittensorEvaluator
from integrations.bittensor.models import (
    BittensorEvaluationWindow, MinerRanking, RankingConfig, RawMinerForecast,
)


async def test_full_ranking_pipeline():
    """End-to-end: evaluator scores miners, computes rankings, verifies good_miner > bad_miner."""
    forecasts = [
        RawMinerForecast(
            window_id="w1", request_uuid="r1", collected_at=datetime(2026, 3, 31),
            miner_uid=1, miner_hotkey="good_miner", stream_id="BTCUSD-5m",
            topic_id=1, schema_id=1, symbol="BTCUSD", timeframe="5m",
            feature_ids=[1, 2, 3, 4, 5], prediction_size=100,
            predictions=[100.0 + i * 0.5 for i in range(100)],
            hashed_predictions=None, hash_verified=True, incentive_score=0.8,
        ),
        RawMinerForecast(
            window_id="w1", request_uuid="r1", collected_at=datetime(2026, 3, 31),
            miner_uid=2, miner_hotkey="bad_miner", stream_id="BTCUSD-5m",
            topic_id=1, schema_id=1, symbol="BTCUSD", timeframe="5m",
            feature_ids=[1, 2, 3, 4, 5], prediction_size=100,
            predictions=[100.0 - i * 0.5 for i in range(100)],
            hashed_predictions=None, hash_verified=True, incentive_score=0.2,
        ),
    ]

    store = AsyncMock()
    store.get_raw_forecasts_by_window = AsyncMock(return_value=forecasts)
    store.save_realized_window = AsyncMock()
    store.save_accuracy_records = AsyncMock()
    store.mark_window_evaluated = AsyncMock()
    store.get_accuracy_rollup = AsyncMock(return_value={
        "good_miner": {
            "windows_evaluated": 50,
            "direction_accuracy": 0.85,
            "mean_magnitude_error": 0.01,
            "mean_path_correlation": 0.7,
        },
        "bad_miner": {
            "windows_evaluated": 50,
            "direction_accuracy": 0.3,
            "mean_magnitude_error": 0.08,
            "mean_path_correlation": -0.1,
        },
    })

    persisted_rankings: list[MinerRanking] = []

    async def capture_ranking(ranking):
        persisted_rankings.append(ranking)

    store.update_miner_ranking = capture_ranking

    adapter = MagicMock()
    adapter.get_incentive_scores = MagicMock(return_value={
        "good_miner": 0.8,
        "bad_miner": 0.2,
    })

    cg = AsyncMock()
    cg.get_ohlc_closes = AsyncMock(return_value=[100.0 + i * 0.3 for i in range(100)])

    evaluator = BittensorEvaluator(
        store=store, data_bus=MagicMock(), event_bus=AsyncMock(),
        coingecko=cg, adapter=adapter,
        ranking_config=RankingConfig(
            min_windows_for_ranking=20,
            alpha_decay_per_window=0.003,
            alpha_floor=0.1,
            lookback_windows=500,
        ),
    )

    window = BittensorEvaluationWindow(
        window_id="w1", symbol="BTCUSD", timeframe="5m",
        collected_at=datetime(2026, 3, 31), prediction_size=100,
    )
    await evaluator._evaluate_window(window)

    assert len(persisted_rankings) == 2
    by_key = {r.miner_hotkey: r for r in persisted_rankings}

    assert by_key["good_miner"].hybrid_score > by_key["bad_miner"].hybrid_score
    assert by_key["good_miner"].direction_accuracy == 0.85
    assert by_key["bad_miner"].direction_accuracy == 0.3
    assert store.mark_window_evaluated.await_count == 1
