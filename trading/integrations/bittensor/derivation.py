from __future__ import annotations

from datetime import datetime, timezone

from integrations.bittensor.models import (
    DerivedBittensorView,
    DerivedMinerSignal,
    RawMinerForecast,
)


def _classify_signal(forecast: RawMinerForecast) -> DerivedMinerSignal:
    predictions = forecast.predictions
    first = predictions[0]
    last = predictions[-1]

    if first == 0:
        expected_return = 0.0
        direction = "flat"
    else:
        expected_return = (last - first) / first
        if expected_return > 0:
            direction = "long"
        elif expected_return < 0:
            direction = "short"
        else:
            direction = "flat"

    if len(predictions) > 1:
        n = len(predictions)
        indices = list(range(n))
        mean_x = (n - 1) / 2
        mean_y = sum(predictions) / n
        numerator = sum((i - mean_x) * (p - mean_y) for i, p in enumerate(predictions))
        denominator = sum((i - mean_x) ** 2 for i in indices)
        path_slope = numerator / denominator if denominator != 0 else 0.0
    else:
        path_slope = 0.0

    if len(predictions) > 1:
        mean_p = sum(predictions) / len(predictions)
        variance = sum((p - mean_p) ** 2 for p in predictions) / len(predictions)
        volatility_proxy = variance**0.5
    else:
        volatility_proxy = 0.0

    confidence_proxy = (
        forecast.incentive_score if forecast.incentive_score is not None else 0.0
    )

    return DerivedMinerSignal(
        window_id=forecast.window_id,
        miner_hotkey=forecast.miner_hotkey,
        symbol=forecast.symbol,
        timeframe=forecast.timeframe,
        direction=direction,
        expected_return=expected_return,
        path_slope=path_slope,
        volatility_proxy=volatility_proxy,
        confidence_proxy=confidence_proxy,
        timestamp=forecast.collected_at,
    )


def _direction_score(direction: str) -> float:
    if direction == "long":
        return 1.0
    if direction == "short":
        return -1.0
    return 0.0


def derive_consensus_view(
    forecasts: list[RawMinerForecast],
    window_id: str,
    symbol: str,
    timeframe: str,
    derivation_version: str,
) -> DerivedBittensorView:
    now = datetime.now(timezone.utc)

    verified = [f for f in forecasts if f.hash_verified]

    if not verified:
        return DerivedBittensorView(
            symbol=symbol,
            timeframe=timeframe,
            window_id=window_id,
            timestamp=now,
            responder_count=0,
            bullish_count=0,
            bearish_count=0,
            flat_count=0,
            weighted_direction=0.0,
            weighted_expected_return=0.0,
            agreement_ratio=0.0,
            equal_weight_direction=0.0,
            equal_weight_expected_return=0.0,
            is_low_confidence=True,
            derivation_version=derivation_version,
        )

    signals = [_classify_signal(f) for f in verified]
    n = len(signals)

    bullish_count = sum(1 for s in signals if s.direction == "long")
    bearish_count = sum(1 for s in signals if s.direction == "short")
    flat_count = sum(1 for s in signals if s.direction == "flat")

    direction_scores = [_direction_score(s.direction) for s in signals]
    expected_returns = [s.expected_return for s in signals]

    equal_weight_direction = sum(direction_scores) / n
    equal_weight_expected_return = sum(expected_returns) / n

    weights = [s.confidence_proxy for s in signals]
    total_weight = sum(weights)

    if total_weight == 0:
        weighted_direction = equal_weight_direction
        weighted_expected_return = equal_weight_expected_return
    else:
        weighted_direction = (
            sum(w * d for w, d in zip(weights, direction_scores)) / total_weight
        )
        weighted_expected_return = (
            sum(w * r for w, r in zip(weights, expected_returns)) / total_weight
        )

    agreement_ratio = max(bullish_count, bearish_count, flat_count) / n

    is_low_confidence = n < 3 or agreement_ratio < 0.5

    return DerivedBittensorView(
        symbol=symbol,
        timeframe=timeframe,
        window_id=window_id,
        timestamp=now,
        responder_count=n,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        flat_count=flat_count,
        weighted_direction=weighted_direction,
        weighted_expected_return=weighted_expected_return,
        agreement_ratio=agreement_ratio,
        equal_weight_direction=equal_weight_direction,
        equal_weight_expected_return=equal_weight_expected_return,
        is_low_confidence=is_low_confidence,
        derivation_version=derivation_version,
    )
