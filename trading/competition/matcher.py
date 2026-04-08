# trading/competition/matcher.py
"""Hourly batch match processor — evaluates signal outcomes, generates matches, updates ELO."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from competition.calibration import CalibrationTracker
from competition.engine import (
    calculate_elo_delta,
    k_factor_for_confidence,
    k_factor_for_new_competitor,
)
from competition.tracker import TrackedSignal

logger = logging.getLogger(__name__)

BASELINE_ELO = 1000
PAIRWISE_WINDOW_MINUTES = 5


class PriceFetcher(Protocol):
    async def get_price(self, asset: str, at: datetime) -> float | None: ...


@dataclass
class MatchResult:
    correct: bool
    return_pct: float
    direction: str


@dataclass
class ProcessingStats:
    signals_processed: int = 0
    baseline_matches: int = 0
    pairwise_matches: int = 0
    skipped_no_price: int = 0


class MatchProcessor:
    """Processes buffered signals into ELO matches."""

    def __init__(
        self,
        store: Any,
        price_fetcher: PriceFetcher,
        calibration: CalibrationTracker | None = None,
        eval_delay_minutes: int = 5,
    ):
        self._store = store
        self._price_fetcher = price_fetcher
        self._calibration = calibration or CalibrationTracker()
        self._eval_delay = eval_delay_minutes

    def evaluate_signal(
        self,
        signal: TrackedSignal,
        price_at_signal: float,
        price_at_eval: float,
    ) -> MatchResult:
        """Determine if a signal was correct based on price movement."""
        pct_change = (price_at_eval - price_at_signal) / price_at_signal

        if signal.direction == "long":
            correct = pct_change > 0
            return_pct = pct_change
        elif signal.direction == "short":
            correct = pct_change < 0
            return_pct = -pct_change  # Short profits on drops
        else:
            correct = False
            return_pct = 0.0

        return MatchResult(
            correct=correct, return_pct=return_pct, direction=signal.direction
        )

    def find_pairwise_matches(
        self,
        signals: list[TrackedSignal],
        window_minutes: int = PAIRWISE_WINDOW_MINUTES,
    ) -> list[tuple[TrackedSignal, TrackedSignal]]:
        """Find pairs of signals on the same asset within the time window."""
        pairs: list[tuple[TrackedSignal, TrackedSignal]] = []
        used: set[int] = set()

        for i, sig_a in enumerate(signals):
            if i in used:
                continue
            for j, sig_b in enumerate(signals[i + 1 :], start=i + 1):
                if j in used:
                    continue
                if sig_a.asset != sig_b.asset:
                    continue
                if sig_a.source_agent == sig_b.source_agent:
                    continue
                dt = abs((sig_a.timestamp - sig_b.timestamp).total_seconds())
                if dt <= window_minutes * 60:
                    pairs.append((sig_a, sig_b))
                    used.add(i)
                    used.add(j)
                    break  # Each signal pairs once

        return pairs

    async def process_batch(self, signals: list[TrackedSignal]) -> ProcessingStats:
        """Process a batch of signals: evaluate, match, update ELO."""
        stats = ProcessingStats(signals_processed=len(signals))
        now = datetime.now(timezone.utc)

        # Evaluate each signal
        evaluated: list[tuple[TrackedSignal, MatchResult]] = []
        for sig in signals:
            price_then = await self._price_fetcher.get_price(sig.asset, sig.timestamp)
            eval_time = sig.timestamp + timedelta(minutes=self._eval_delay)
            if eval_time > now:
                continue  # Not enough time elapsed
            price_now = await self._price_fetcher.get_price(sig.asset, eval_time)

            if price_then is None or price_now is None:
                stats.skipped_no_price += 1
                continue

            result = self.evaluate_signal(sig, price_then, price_now)
            evaluated.append((sig, result))

        # Baseline matches: each signal vs Hodler
        for sig, result in evaluated:
            await self._process_baseline_match(sig, result)
            stats.baseline_matches += 1

            # Record calibration
            band = self._confidence_band(sig.confidence)
            self._calibration.record(sig.source_agent, band, correct=result.correct)

        # Pairwise matches
        pairs = self.find_pairwise_matches([s for s, _ in evaluated])
        result_map = {id(s): r for s, r in evaluated}
        for sig_a, sig_b in pairs:
            r_a = result_map.get(id(sig_a))
            r_b = result_map.get(id(sig_b))
            if r_a and r_b:
                await self._process_pairwise_match(sig_a, r_a, sig_b, r_b)
                stats.pairwise_matches += 1

        logger.info(
            "competition.matcher: processed %d signals, %d baseline, %d pairwise, %d skipped",
            stats.signals_processed,
            stats.baseline_matches,
            stats.pairwise_matches,
            stats.skipped_no_price,
        )
        return stats

    async def _process_baseline_match(
        self, sig: TrackedSignal, result: MatchResult
    ) -> None:
        """Evaluate signal against buy-and-hold baseline."""
        record = None
        for comp_type in ["agent", "miner", "provider"]:
            record = await self._store.get_competitor_by_ref(
                comp_type, sig.source_agent
            )
            if record:
                break
        if not record:
            return

        comp_id = str(record["id"])
        current_elo = await self._store.get_elo(comp_id, sig.asset)

        # Determine K-factor
        band = self._confidence_band(sig.confidence)
        effective_band = self._calibration.effective_band(sig.source_agent, band)
        confidence_k = k_factor_for_confidence(
            {"high": 0.9, "medium": 0.7, "low": 0.3}.get(effective_band, 0.5)
        )

        outcome = 1.0 if result.correct else 0.0
        delta = calculate_elo_delta(current_elo, BASELINE_ELO, outcome, k=confidence_k)
        new_elo = current_elo + delta

        await self._store.update_elo(comp_id, sig.asset, new_elo, delta)

    async def _process_pairwise_match(
        self,
        sig_a: TrackedSignal,
        result_a: MatchResult,
        sig_b: TrackedSignal,
        result_b: MatchResult,
    ) -> None:
        """Head-to-head match between two signals on same asset."""
        rec_a = await self._store.get_competitor_by_ref("agent", sig_a.source_agent)
        rec_b = await self._store.get_competitor_by_ref("agent", sig_b.source_agent)
        if not rec_a or not rec_b:
            return

        id_a, id_b = str(rec_a["id"]), str(rec_b["id"])
        elo_a = await self._store.get_elo(id_a, sig_a.asset)
        elo_b = await self._store.get_elo(id_b, sig_b.asset)

        # Determine winner by return
        if result_a.return_pct > result_b.return_pct:
            outcome_a, outcome_b = 1.0, 0.0
        elif result_b.return_pct > result_a.return_pct:
            outcome_a, outcome_b = 0.0, 1.0
        else:
            outcome_a, outcome_b = 0.5, 0.5  # Draw

        k = 20  # Standard K for pairwise
        delta_a = calculate_elo_delta(elo_a, elo_b, outcome_a, k=k)
        delta_b = calculate_elo_delta(elo_b, elo_a, outcome_b, k=k)

        await self._store.update_elo(id_a, sig_a.asset, elo_a + delta_a, delta_a)
        await self._store.update_elo(id_b, sig_b.asset, elo_b + delta_b, delta_b)

    @staticmethod
    def _confidence_band(confidence: float) -> str:
        if confidence >= 0.8:
            return "high"
        if confidence >= 0.5:
            return "medium"
        return "low"
