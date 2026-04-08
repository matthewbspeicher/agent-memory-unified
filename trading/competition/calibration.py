# trading/competition/calibration.py
"""Confidence calibration tracking — clamps K-factor band if accuracy is poor."""

from __future__ import annotations

from collections import defaultdict, deque


BAND_ORDER = ["high", "medium", "low"]
BAND_DEMOTION = {"high": "medium", "medium": "low", "low": "low"}


class CalibrationTracker:
    """Rolling window accuracy tracker per competitor per confidence band."""

    def __init__(self, window_size: int = 100, clamp_threshold: float = 0.65):
        self._window_size = window_size
        self._clamp_threshold = clamp_threshold
        # {(competitor_ref, band): deque of bools}
        self._records: dict[tuple[str, str], deque[bool]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

    def record(self, competitor_ref: str, band: str, *, correct: bool) -> None:
        """Record a signal outcome for calibration tracking."""
        self._records[(competitor_ref, band)].append(correct)

    def get_calibration(self, competitor_ref: str, band: str) -> float:
        """Get accuracy score for a competitor at a confidence band. 0.0-1.0."""
        records = self._records.get((competitor_ref, band))
        if not records:
            return 1.0  # No data = assume calibrated
        return sum(records) / len(records)

    def should_clamp(self, competitor_ref: str, band: str) -> bool:
        """True if competitor's accuracy at this band is below threshold."""
        records = self._records.get((competitor_ref, band))
        if not records or len(records) < 5:
            return False  # Need minimum samples
        return self.get_calibration(competitor_ref, band) < self._clamp_threshold

    def effective_band(self, competitor_ref: str, claimed_band: str) -> str:
        """Return the effective confidence band after clamping."""
        if self.should_clamp(competitor_ref, claimed_band):
            return BAND_DEMOTION.get(claimed_band, claimed_band)
        return claimed_band
