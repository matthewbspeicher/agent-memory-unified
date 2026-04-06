from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from data.coingecko import SYMBOL_TO_COINGECKO
from integrations.bittensor.models import (
    BittensorMetrics,
    MinerAccuracyRecord,
    MinerRankingInput,
    RankingConfig,
    RealizedWindowSnapshot,
)
from integrations.bittensor.ranking import compute_rankings, DIRECTION_HEAVY

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure scoring functions
# ---------------------------------------------------------------------------


def compute_direction_correct(predicted: list[float], actual: list[float]) -> bool:
    """Return True if the sign of total predicted change matches actual change."""
    if not predicted or not actual:
        return False
    predicted_return = predicted[-1] - predicted[0]
    actual_return = actual[-1] - actual[0]
    if predicted_return == 0.0 or actual_return == 0.0:
        return False
    return (predicted_return > 0) == (actual_return > 0)


def compute_magnitude_error(predicted_return: float, actual_return: float) -> float:
    """Return absolute difference between predicted and actual return."""
    return abs(predicted_return - actual_return)


def compute_path_correlation(
    predicted: list[float], actual: list[float]
) -> float | None:
    """Return Pearson correlation between predicted and actual price paths.

    Returns None if either series is too short (< 2) or has zero variance.
    """
    n = len(predicted)
    if n < 2 or len(actual) < 2:
        return None

    m = min(n, len(actual))
    p = predicted[:m]
    a = actual[:m]

    mean_p = sum(p) / m
    mean_a = sum(a) / m

    cov = sum((p[i] - mean_p) * (a[i] - mean_a) for i in range(m))
    var_p = sum((x - mean_p) ** 2 for x in p)
    var_a = sum((x - mean_a) ** 2 for x in a)

    if var_p == 0.0 or var_a == 0.0:
        return None

    return cov / (var_p**0.5 * var_a**0.5)


# ---------------------------------------------------------------------------
# BittensorEvaluator
# ---------------------------------------------------------------------------


class BittensorEvaluator:
    """Periodically scores miner forecasts against realized market data.

    The evaluation loop queries the store for mature unevaluated windows,
    fetches realized bars via CoinGecko, and computes per-miner accuracy records.
    """

    supports_evaluation = True

    def __init__(
        self,
        store,
        data_bus,
        event_bus,
        *,
        delay_factor: float = 1.1,
        prediction_size: int = 100,
        timeframe_minutes: int = 5,
        scoring_version: str = "v1",
        check_interval: float = 60.0,
        coingecko=None,
        adapter=None,
        ranking_config: RankingConfig | None = None,
        metrics: BittensorMetrics | None = None,
    ) -> None:
        self._store = store
        self._data_bus = data_bus
        self._event_bus = event_bus
        self._delay_factor = delay_factor
        self._prediction_size = prediction_size
        self._timeframe_minutes = timeframe_minutes
        self._scoring_version = scoring_version
        self._check_interval = check_interval
        self._coingecko = coingecko
        self._adapter = adapter
        self._ranking_config = ranking_config or RankingConfig(
            min_windows_for_ranking=20,
            alpha_decay_per_window=0.003,
            alpha_floor=0.1,
            lookback_windows=500,
        )
        self._running = False
        self.last_success_at: datetime | None = None
        self.windows_evaluated_total: int = 0
        self.unevaluated_count: int = 0
        self.metrics = metrics or BittensorMetrics()

    async def run(self) -> None:
        """Main async evaluation loop."""
        self._running = True
        logger.info(
            "BittensorEvaluator started (delay_factor=%.2f, prediction_size=%d, "
            "timeframe_minutes=%d, check_interval=%.1fs)",
            self._delay_factor,
            self._prediction_size,
            self._timeframe_minutes,
            self._check_interval,
        )
        while self._running:
            try:
                await self._evaluate_mature_windows()
            except Exception:
                logger.exception("BittensorEvaluator: error during evaluation cycle")
            await asyncio.sleep(self._check_interval)

    async def _evaluate_mature_windows(self) -> None:
        """Query store for unevaluated mature windows and evaluate each."""
        # Strip tzinfo to match the store's naive-datetime convention (SQLite TEXT columns)
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)

        # Expire stale pending windows (>2h old)
        expired = await self._store.expire_stale_windows(now=now, ttl_hours=2)
        if expired:
            self.metrics.windows_expired += expired
            logger.info("BittensorEvaluator: expired %d stale windows", expired)
            await self._event_bus.publish(
                "bittensor.window_expired", {"count": expired}
            )

        windows = await self._store.get_unevaluated_windows(
            now=now,
            delay_factor=self._delay_factor,
            prediction_size=self._prediction_size,
            timeframe_minutes=self._timeframe_minutes,
        )
        self.unevaluated_count = len(windows)
        if not windows:
            logger.debug("BittensorEvaluator: no mature windows to evaluate")
            return

        logger.info("BittensorEvaluator: evaluating %d mature windows", len(windows))
        for window in windows:
            try:
                await self._evaluate_window(window)
            except Exception:
                logger.exception(
                    "BittensorEvaluator: error evaluating window %s", window.window_id
                )

    async def _evaluate_window(self, window) -> None:
        """Fetch realized bars and compute per-miner accuracy for one window."""
        eval_start = datetime.now(tz=timezone.utc)
        if self._coingecko is None or window.symbol not in SYMBOL_TO_COINGECKO:
            reason = "no_coingecko_or_unknown_symbol"
            self.metrics.windows_skipped += 1
            self.metrics.last_skip_reason = reason
            logger.warning(
                "BittensorEvaluator: skipping window %s — %s (symbol=%s)",
                window.window_id,
                reason,
                window.symbol,
            )
            await self._event_bus.publish(
                "bittensor.evaluation_skipped",
                {"window_id": window.window_id, "symbol": window.symbol, "reason": reason},
            )
            return

        all_forecasts = await self._store.get_raw_forecasts_by_window(window.window_id)
        forecasts = [f for f in all_forecasts if getattr(f, "hash_verified", True)]
        if not forecasts:
            reason = "no_verified_forecasts"
            self.metrics.windows_skipped += 1
            self.metrics.last_skip_reason = reason
            logger.warning(
                "BittensorEvaluator: skipping window %s — %s",
                window.window_id,
                reason,
            )
            await self._event_bus.publish(
                "bittensor.evaluation_skipped",
                {"window_id": window.window_id, "symbol": window.symbol, "reason": reason},
            )
            return

        coin_id = SYMBOL_TO_COINGECKO[window.symbol]
        realized = await self._coingecko.get_ohlc_closes(
            coin_id, window.prediction_size
        )

        if len(realized) < window.prediction_size * 0.9:
            reason = "insufficient_candle_data"
            self.metrics.windows_skipped += 1
            self.metrics.last_skip_reason = reason
            logger.warning(
                "BittensorEvaluator: skipping window %s — %s (got %d, need ~%d)",
                window.window_id,
                reason,
                len(realized),
                window.prediction_size,
            )
            await self._event_bus.publish(
                "bittensor.evaluation_skipped",
                {"window_id": window.window_id, "symbol": window.symbol, "reason": reason},
            )
            return

        actual_return = realized[-1] - realized[0] if realized else 0.0
        snapshot = RealizedWindowSnapshot(
            window_id=window.window_id,
            symbol=window.symbol,
            timeframe=window.timeframe,
            realized_path=realized,
            realized_return=actual_return,
            bars_used=len(realized),
            source="coingecko",
            captured_at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )
        await self._store.save_realized_window(snapshot)

        records: list[MinerAccuracyRecord] = []
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        for forecast in forecasts:
            predicted_return = (
                forecast.predictions[-1] - forecast.predictions[0]
                if forecast.predictions
                else 0.0
            )
            record = MinerAccuracyRecord(
                window_id=window.window_id,
                miner_hotkey=forecast.miner_hotkey,
                symbol=window.symbol,
                timeframe=window.timeframe,
                direction_correct=compute_direction_correct(
                    forecast.predictions, realized
                ),
                predicted_return=predicted_return,
                actual_return=actual_return,
                magnitude_error=compute_magnitude_error(
                    predicted_return, actual_return
                ),
                path_correlation=compute_path_correlation(
                    forecast.predictions, realized
                ),
                outcome_bars=len(realized),
                scoring_version=self._scoring_version,
                evaluated_at=now,
            )
            records.append(record)

        await self._store.save_accuracy_records(records)

        # --- Ranking orchestration ---
        hotkeys = list({r.miner_hotkey for r in records})
        rollups = await self._store.get_accuracy_rollup(
            hotkeys, self._ranking_config.lookback_windows
        )
        incentive_scores = (
            self._adapter.get_incentive_scores(hotkeys)
            if self._adapter is not None
            else {hk: 0.0 for hk in hotkeys}
        )
        inputs: list[MinerRankingInput] = []
        for hk in hotkeys:
            rollup = rollups.get(hk)
            if rollup is None:
                continue
            inputs.append(
                MinerRankingInput(
                    miner_hotkey=hk,
                    windows_evaluated=rollup["windows_evaluated"],
                    direction_accuracy=rollup["direction_accuracy"],
                    mean_magnitude_error=rollup["mean_magnitude_error"],
                    mean_path_correlation=rollup["mean_path_correlation"],
                    raw_incentive_score=incentive_scores.get(hk, 0.0),
                )
            )

        rankings = compute_rankings(inputs, DIRECTION_HEAVY, self._ranking_config, now)
        for ranking in rankings:
            await self._store.update_miner_ranking(ranking)

        await self._store.mark_window_evaluated(window.window_id)

        self.windows_evaluated_total += 1
        self.last_success_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        self.metrics.windows_evaluated += 1
        self.metrics.last_evaluation_duration_secs = (
            datetime.now(tz=timezone.utc) - eval_start
        ).total_seconds()

        await self._event_bus.publish(
            "bittensor.accuracy_evaluated",
            {
                "window_id": window.window_id,
                "symbol": window.symbol,
                "timeframe": window.timeframe,
                "miners_scored": len(records),
                "miners_ranked": len(rankings),
                "scoring_version": self._scoring_version,
            },
        )

    def stop(self) -> None:
        """Signal the evaluation loop to stop after the current cycle."""
        logger.info("BittensorEvaluator stopping")
        self._running = False
