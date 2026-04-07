"""MinerEvaluator — evaluates Bittensor miner forecasts against historical market data."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

from broker.models import Bar, Symbol, AssetType
from data.bus import DataBus
from integrations.bittensor.models import (
    BittensorEvaluationWindow,
    MinerAccuracyRecord,
    RawMinerForecast,
    RealizedWindowSnapshot,
    MinerRankingInput,
    RankingConfig,
    RankingWeights,
)
from integrations.bittensor.ranking import compute_rankings, DIRECTION_HEAVY
from storage.bittensor import BittensorStore

logger = logging.getLogger(__name__)


class MinerEvaluator:
    """Orchestrates the evaluation of pending miner forecasts."""

    def __init__(self, store: BittensorStore, data_bus: DataBus):
        self.store = store
        self.data_bus = data_bus

    async def evaluate_pending_windows(self, now: datetime | None = None) -> int:
        """Fetch unevaluated windows and realize their outcomes."""
        now = now or datetime.now(timezone.utc)

        # 1. Find windows that have matured
        windows = await self.store.get_unevaluated_windows(
            now=now,
            delay_factor=1.1,  # 10% safety buffer
            prediction_size=100,  # Default if not found in DB
            timeframe_minutes=5,  # Default
        )

        if not windows:
            logger.debug("No pending windows mature for evaluation")
            return 0

        logger.info("Found %d pending windows to evaluate", len(windows))
        evaluated_count = 0

        for window in windows:
            try:
                await self._evaluate_window(window)
                evaluated_count += 1
            except Exception as e:
                logger.error(
                    "Failed to evaluate window %s: %s",
                    window.window_id,
                    e,
                    exc_info=True,
                )

        # After evaluating windows, refresh rankings
        if evaluated_count > 0:
            await self.refresh_rankings()

        return evaluated_count

    async def _evaluate_window(self, window: BittensorEvaluationWindow):
        """Realize one window: fetch prices, score all miners, update rankings."""
        symbol = Symbol(
            ticker=window.symbol, asset_type=AssetType.FOREX
        )  # Most BT signals are FX

        # 1. Fetch historical bars for the evaluation period
        # We need bars starting from collected_at
        bars = await self.data_bus.get_historical(
            symbol=symbol,
            timeframe=window.timeframe,
            period="1d",  # Plenty of buffer
        )

        if not bars:
            logger.warning(
                "No bar data for %s, skipping window %s",
                window.symbol,
                window.window_id,
            )
            return

        # 2. Extract realized path
        # Find bars that match the prediction window
        window_bars = [b for b in bars if b.timestamp >= window.collected_at]
        if len(window_bars) < window.prediction_size:
            logger.debug(
                "Not enough bars yet for window %s (%d/%d)",
                window.window_id,
                len(window_bars),
                window.prediction_size,
            )
            return

        evaluation_bars = window_bars[: window.prediction_size]
        realized_prices = [float(b.close) for b in evaluation_bars]
        start_price = float(evaluation_bars[0].open)
        end_price = float(evaluation_bars[-1].close)
        actual_return = (end_price - start_price) / start_price

        # 3. Save realized window snapshot
        realized_snapshot = RealizedWindowSnapshot(
            window_id=window.window_id,
            symbol=window.symbol,
            timeframe=window.timeframe,
            realized_path=realized_prices,
            realized_return=actual_return,
            bars_used=len(realized_prices),
            source="yahoo",
            captured_at=datetime.now(timezone.utc),
        )
        await self.store.save_realized_window(realized_snapshot)

        # 4. Evaluate each miner's forecast
        forecasts = await self.store.get_raw_forecasts_by_window(window.window_id)
        accuracy_records = []

        for f in forecasts:
            record = self._score_forecast(f, realized_prices, actual_return)
            accuracy_records.append(record)

        if accuracy_records:
            await self.store.save_accuracy_records(accuracy_records)
            await self.store.mark_window_evaluated(window.window_id)
            logger.info(
                "Evaluated %d forecasts for window %s",
                len(accuracy_records),
                window.window_id,
            )

    def _score_forecast(
        self, forecast: RawMinerForecast, actual_path: list[float], actual_return: float
    ) -> MinerAccuracyRecord:
        """Compute accuracy metrics for a single miner's predictions."""
        predicted_path = forecast.predictions
        predicted_return = (
            (predicted_path[-1] - predicted_path[0]) / predicted_path[0]
            if predicted_path
            else 0.0
        )

        direction_correct = (predicted_return * actual_return) > 0
        if abs(predicted_return) < 0.0001 and abs(actual_return) < 0.0001:
            direction_correct = True  # Both flat

        magnitude_error = abs(predicted_return - actual_return)

        # Path correlation (Pearson)
        path_corr = None
        if len(predicted_path) == len(actual_path) and len(predicted_path) > 1:
            try:
                import numpy as np

                path_corr = float(np.corrcoef(predicted_path, actual_path)[0, 1])
            except Exception:
                pass

        return MinerAccuracyRecord(
            window_id=forecast.window_id,
            miner_hotkey=forecast.miner_hotkey,
            symbol=forecast.symbol,
            timeframe=forecast.timeframe,
            direction_correct=direction_correct,
            predicted_return=predicted_return,
            actual_return=actual_return,
            magnitude_error=magnitude_error,
            path_correlation=path_corr,
            outcome_bars=len(actual_path),
            scoring_version="v1",
            evaluated_at=datetime.now(timezone.utc),
        )

    def _determine_lifecycle_status(self, miner_data: MinerRankingInput) -> str:
        """Apply Vanta network rules for elimination and probation."""
        # 10% maximum drawdown elimination rule
        if miner_data.max_drawdown >= 0.10:
            return "eliminated"

        # Probation for consistent underperformance (e.g., <30% accuracy after 20 windows)
        if miner_data.windows_evaluated >= 20 and miner_data.direction_accuracy < 0.30:
            return "probation"

        return "active"

    async def refresh_rankings(self):
        """Aggregate accuracy records and update miner rankings in the store."""
        config = RankingConfig(
            min_windows_for_ranking=5,
            alpha_decay_per_window=0.05,
            alpha_floor=0.1,
            lookback_windows=50,
        )

        async with self.store._db.execute(
            "SELECT DISTINCT miner_hotkey FROM bittensor_accuracy_records"
        ) as cursor:
            hotkeys = [row[0] for row in await cursor.fetchall()]

        if not hotkeys:
            return

        rollups = await self.store.get_accuracy_rollup(hotkeys, config.lookback_windows)

        inputs = []

        # Batch fetch all incentive scores in a single query
        if hotkeys:
            placeholders = ",".join("?" * len(hotkeys))
            async with self.store._db.execute(
                f"SELECT miner_hotkey, incentive_score FROM bittensor_raw_forecasts "
                f"WHERE miner_hotkey IN ({placeholders}) "
                f"ORDER BY collected_at DESC",
                tuple(hotkeys),
            ) as cursor:
                rows = await cursor.fetchall()

            # Create a dict of hotkey -> incentive (most recent per hotkey)
            incentive_map = {}
            for hotkey, incentive in rows:
                if hotkey not in incentive_map:
                    incentive_map[hotkey] = incentive if incentive is not None else 0.0

        for hotkey, r in rollups.items():
            incentive = incentive_map.get(hotkey, 0.0)
            inputs.append(
                MinerRankingInput(
                    miner_hotkey=hotkey,
                    windows_evaluated=r["windows_evaluated"],
                    direction_accuracy=r["direction_accuracy"],
                    mean_magnitude_error=r["mean_magnitude_error"],
                    mean_path_correlation=r["mean_path_correlation"],
                    raw_incentive_score=incentive,
                )
            )

        rankings = compute_rankings(
            inputs=inputs,
            weights=DIRECTION_HEAVY,
            config=config,
            now=datetime.now(timezone.utc),
        )

        for rank in rankings:
            await self.store.update_miner_ranking(rank)

        logger.info("Refreshed rankings for %d miners", len(rankings))

    async def run(self, interval_seconds: float = 300.0):
        """Run the periodic evaluation loop."""
        logger.info("MinerEvaluator loop started (interval: %.1fs)", interval_seconds)
        while True:
            try:
                evaluated = await self.evaluate_pending_windows()
                if evaluated > 0:
                    logger.info("MinerEvaluator: evaluated %d windows", evaluated)
            except Exception as e:
                logger.error("MinerEvaluator loop error: %s", e, exc_info=True)

            await asyncio.sleep(interval_seconds)
