from __future__ import annotations
from datetime import datetime

from integrations.bittensor.derivation import derive_consensus_view
from integrations.bittensor.models import RawMinerForecast


def _forecast(hotkey: str, predictions: list[float], incentive: float = 0.5, hash_verified: bool = True) -> RawMinerForecast:
    return RawMinerForecast(
        window_id="w1",
        request_uuid="req1",
        collected_at=datetime(2026, 3, 28, 12, 0),
        miner_uid=1,
        miner_hotkey=hotkey,
        stream_id="BTCUSD-5m",
        topic_id=1,
        schema_id=1,
        symbol="BTCUSD",
        timeframe="5m",
        feature_ids=[1, 2, 3, 4, 5],
        prediction_size=5,
        predictions=predictions,
        hashed_predictions=None,
        hash_verified=hash_verified,
        incentive_score=incentive,
    )


def test_all_bullish():
    forecasts = [
        _forecast("hk1", [100, 101, 102, 103, 104], incentive=0.5),
        _forecast("hk2", [100, 102, 104, 106, 108], incentive=0.8),
    ]
    view = derive_consensus_view(forecasts, "w1", "BTCUSD", "5m", "v1")
    assert view.bullish_count == 2
    assert view.bearish_count == 0
    assert view.flat_count == 0
    assert view.equal_weight_direction > 0
    assert view.weighted_direction > 0
    assert view.agreement_ratio == 1.0


def test_all_bearish():
    forecasts = [
        _forecast("hk1", [100, 99, 98, 97, 96]),
        _forecast("hk2", [100, 98, 96, 94, 92]),
    ]
    view = derive_consensus_view(forecasts, "w1", "BTCUSD", "5m", "v1")
    assert view.bearish_count == 2
    assert view.equal_weight_direction < 0


def test_mixed_direction():
    forecasts = [
        _forecast("hk1", [100, 101, 102, 103, 104]),
        _forecast("hk2", [100, 99, 98, 97, 96]),
        _forecast("hk3", [100, 101, 102, 103, 104]),
    ]
    view = derive_consensus_view(forecasts, "w1", "BTCUSD", "5m", "v1")
    assert view.bullish_count == 2
    assert view.bearish_count == 1
    assert view.agreement_ratio < 1.0
    assert view.responder_count == 3


def test_hash_failed_excluded():
    forecasts = [
        _forecast("hk1", [100, 101, 102, 103, 104], hash_verified=True),
        _forecast("hk2", [100, 99, 98, 97, 96], hash_verified=False),
    ]
    view = derive_consensus_view(forecasts, "w1", "BTCUSD", "5m", "v1")
    assert view.responder_count == 1
    assert view.bullish_count == 1


def test_single_miner():
    forecasts = [_forecast("hk1", [100, 101, 102, 103, 104])]
    view = derive_consensus_view(forecasts, "w1", "BTCUSD", "5m", "v1")
    assert view.responder_count == 1
    assert view.agreement_ratio == 1.0


def test_incentive_weighting():
    forecasts = [
        _forecast("hk1", [100, 101, 102, 103, 104], incentive=0.1),
        _forecast("hk2", [100, 99, 98, 97, 96], incentive=0.9),
    ]
    view = derive_consensus_view(forecasts, "w1", "BTCUSD", "5m", "v1")
    assert view.weighted_direction < 0


def test_empty_forecasts_low_confidence():
    view = derive_consensus_view([], "w1", "BTCUSD", "5m", "v1")
    assert view.is_low_confidence is True
    assert view.responder_count == 0


def test_flat_predictions():
    forecasts = [_forecast("hk1", [100, 100, 100, 100, 100])]
    view = derive_consensus_view(forecasts, "w1", "BTCUSD", "5m", "v1")
    assert view.flat_count == 1
    assert view.bullish_count == 0
    assert view.bearish_count == 0
