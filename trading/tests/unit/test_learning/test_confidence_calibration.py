from __future__ import annotations

import aiosqlite
import pytest

from storage.db import init_db
from storage.confidence_calibration import ConfidenceCalibrationStore
from learning.confidence_calibration import (
    ConfidenceCalibrationConfig,
    assign_bucket,
    classify_sample_quality,
    compute_multiplier,
    compute_calibrated_score,
    build_recommendation,
    apply_composed_kelly_cap,
    recompute_calibration_for_strategy,
)


@pytest.fixture
def cfg():
    return ConfidenceCalibrationConfig()


@pytest.fixture
async def cal_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield ConfidenceCalibrationStore(db)
    await db.close()


# ---------------------------------------------------------------------------
# Bucket assignment
# ---------------------------------------------------------------------------

class TestAssignBucket:
    def test_none_returns_unknown(self):
        assert assign_bucket(None) == "unknown"

    def test_zero(self):
        assert assign_bucket(0.0) == "0.00-0.10"

    def test_mid_range(self):
        assert assign_bucket(0.75) == "0.70-0.80"

    def test_exactly_0_70(self):
        # 0.70 is the lower bound of the 0.70-0.80 bucket
        assert assign_bucket(0.70) == "0.70-0.80"

    def test_exactly_0_80(self):
        # 0.80 is the lower bound of the 0.80-0.90 bucket
        assert assign_bucket(0.80) == "0.80-0.90"

    def test_exactly_1_0(self):
        assert assign_bucket(1.0) == "0.90-1.00"

    def test_below_zero_clamped(self):
        assert assign_bucket(-0.5) == "0.00-0.10"

    def test_above_one_clamped(self):
        assert assign_bucket(1.5) == "0.90-1.00"

    def test_low_value(self):
        assert assign_bucket(0.05) == "0.00-0.10"

    def test_high_value(self):
        assert assign_bucket(0.95) == "0.90-1.00"

    def test_decimal_boundary(self):
        assert assign_bucket(0.10) == "0.10-0.20"
        assert assign_bucket(0.20) == "0.20-0.30"
        assert assign_bucket(0.90) == "0.90-1.00"

    def test_format_2dp(self):
        """Bucket labels always have 2 decimal places."""
        bucket = assign_bucket(0.35)
        assert bucket == "0.30-0.40"
        low, high = bucket.split("-")
        assert "." in low and len(low.split(".")[1]) == 2
        assert "." in high and len(high.split(".")[1]) == 2


# ---------------------------------------------------------------------------
# Sample quality classification
# ---------------------------------------------------------------------------

class TestClassifySampleQuality:
    def test_insufficient(self):
        assert classify_sample_quality(0) == "insufficient"
        assert classify_sample_quality(9) == "insufficient"

    def test_weak(self):
        assert classify_sample_quality(10) == "weak"
        assert classify_sample_quality(24) == "weak"

    def test_usable(self):
        assert classify_sample_quality(25) == "usable"
        assert classify_sample_quality(49) == "usable"

    def test_strong(self):
        assert classify_sample_quality(50) == "strong"
        assert classify_sample_quality(1000) == "strong"


# ---------------------------------------------------------------------------
# Multiplier computation
# ---------------------------------------------------------------------------

class TestComputeMultiplier:
    def test_insufficient_returns_fallback(self, cfg):
        m = compute_multiplier(0.02, "insufficient", cfg)
        assert m == cfg.insufficient_sample_multiplier

    def test_none_expectancy_returns_fallback(self, cfg):
        m = compute_multiplier(None, "strong", cfg)
        assert m == cfg.insufficient_sample_multiplier

    def test_negative_expectancy_returns_025(self, cfg):
        m = compute_multiplier(-0.01, "strong", cfg)
        assert m == 0.25

    def test_zero_expectancy_returns_025(self, cfg):
        m = compute_multiplier(0.0, "strong", cfg)
        assert m == 0.25

    def test_weak_positive_returns_05(self, cfg):
        m = compute_multiplier(0.003, "strong", cfg)
        assert m == 0.5

    def test_moderate_positive_returns_075(self, cfg):
        m = compute_multiplier(0.010, "strong", cfg)
        assert m == 0.75

    def test_strong_positive_returns_1(self, cfg):
        m = compute_multiplier(0.020, "strong", cfg)
        assert m == 1.0

    def test_exceptional_strong_sample_returns_125(self, cfg):
        m = compute_multiplier(0.04, "strong", cfg)
        assert m == 1.25

    def test_exceptional_weak_sample_capped_at_1(self, cfg):
        """Exceptional expectancy but weak/usable sample → capped at 1.0x, not 1.25x."""
        m_usable = compute_multiplier(0.04, "usable", cfg)
        assert m_usable == 1.0
        m_weak = compute_multiplier(0.04, "weak", cfg)
        assert m_weak == 1.0

    def test_multiplier_never_zero(self, cfg):
        """Multiplier floor is always 0.25x — 0.0x is the filter stage's job."""
        for expectancy in [-0.5, -0.1, -0.001, 0.0]:
            m = compute_multiplier(expectancy, "strong", cfg)
            assert m >= 0.25, f"Expected >= 0.25 for expectancy={expectancy}, got {m}"

    def test_multiplier_never_exceeds_max(self, cfg):
        m = compute_multiplier(999.0, "strong", cfg)
        assert m <= cfg.max_positive_multiplier


# ---------------------------------------------------------------------------
# Calibrated score
# ---------------------------------------------------------------------------

class TestComputeCalibratedScore:
    def test_none_expectancy(self):
        assert compute_calibrated_score(None, "strong") is None

    def test_insufficient_zero_weight(self):
        score = compute_calibrated_score(0.05, "insufficient")
        assert score == 0.0

    def test_weak_quarter_weight(self):
        score = compute_calibrated_score(0.04, "weak")
        assert score == pytest.approx(0.01)

    def test_usable_weight(self):
        score = compute_calibrated_score(0.02, "usable")
        assert score == pytest.approx(0.012)

    def test_strong_full_weight(self):
        score = compute_calibrated_score(0.03, "strong")
        assert score == pytest.approx(0.03)


# ---------------------------------------------------------------------------
# build_recommendation
# ---------------------------------------------------------------------------

class TestBuildRecommendation:
    def test_unknown_bucket(self, cfg):
        rec = build_recommendation("unknown", 0, None, None, cfg)
        assert rec.bucket == "unknown"
        assert rec.sample_quality == "insufficient"
        assert rec.would_reject is False
        assert "Unknown confidence" in rec.reason

    def test_insufficient_sample_no_reject(self, cfg):
        rec = build_recommendation("0.70-0.80", 5, -0.05, -10.0, cfg)
        assert rec.sample_quality == "insufficient"
        assert rec.would_reject is False
        assert rec.multiplier == cfg.insufficient_sample_multiplier

    def test_negative_expectancy_allow_reject_false(self, cfg):
        """allow_reject=False → never rejects regardless of expectancy."""
        rec = build_recommendation("0.70-0.80", 60, -0.05, -50.0, cfg)
        assert rec.would_reject is False
        assert rec.multiplier == 0.25

    def test_negative_expectancy_allow_reject_true(self):
        cfg_with_reject = ConfidenceCalibrationConfig(allow_reject=True)
        rec = build_recommendation("0.70-0.80", 60, -0.05, -50.0, cfg_with_reject)
        assert rec.would_reject is True
        assert "rejected" in rec.reason.lower()

    def test_hard_reject_requires_min_trades(self):
        cfg_with_reject = ConfidenceCalibrationConfig(allow_reject=True)
        # Only 30 trades — below min_trades_for_hard_reject=50
        rec = build_recommendation("0.70-0.80", 30, -0.05, -50.0, cfg_with_reject)
        assert rec.would_reject is False

    def test_strong_positive_produces_full_multiplier(self, cfg):
        rec = build_recommendation("0.70-0.80", 50, 0.02, 20.0, cfg)
        assert rec.sample_quality == "strong"
        assert rec.multiplier == 1.0
        assert rec.would_reject is False

    def test_exceptional_strong_produces_125(self, cfg):
        rec = build_recommendation("0.70-0.80", 100, 0.05, 50.0, cfg)
        assert rec.multiplier == 1.25

    def test_calibrated_score_populated(self, cfg):
        rec = build_recommendation("0.70-0.80", 50, 0.02, 20.0, cfg)
        assert rec.calibrated_score is not None
        assert rec.calibrated_score > 0


# ---------------------------------------------------------------------------
# Composed Kelly cap
# ---------------------------------------------------------------------------

class TestApplyComposedKellyCap:
    def test_no_cap_needed(self):
        result = apply_composed_kelly_cap(0.25, 1.0, 0.50)
        assert result == 1.0

    def test_cap_applied(self):
        # 0.50 base * 1.25x = 0.625 → exceeds 0.50 cap
        result = apply_composed_kelly_cap(0.50, 1.25, 0.50)
        assert result == pytest.approx(1.0)

    def test_zero_kelly_unchanged(self):
        result = apply_composed_kelly_cap(0.0, 1.25, 0.50)
        assert result == 1.25

    def test_exact_cap_boundary(self):
        result = apply_composed_kelly_cap(0.40, 1.25, 0.50)
        # 0.40 * 1.25 = 0.50 → exactly at cap, no reduction needed
        assert result == pytest.approx(1.25)

    def test_aggressive_kelly(self):
        # 0.50 base * 1.25x = 0.625 > 0.50 → reduce multiplier
        adjusted = apply_composed_kelly_cap(0.50, 1.25, 0.50)
        composed = 0.50 * adjusted
        assert composed <= 0.50 + 1e-9


# ---------------------------------------------------------------------------
# recompute_calibration_for_strategy
# ---------------------------------------------------------------------------

def _make_analytics_row(confidence: float | None, net_pnl: str, net_return: float, outcome: str, exit_time: str = "2026-03-25T14:00:00") -> dict:
    return {
        "confidence": confidence,
        "net_pnl": net_pnl,
        "net_return_pct": net_return,
        "realized_outcome": outcome,
        "exit_time": exit_time,
    }


class TestRecomputeCalibration:
    async def test_basic_recompute(self, cal_store: ConfidenceCalibrationStore):
        rows = [
            _make_analytics_row(0.75, "50.00", 0.02, "win"),
            _make_analytics_row(0.72, "30.00", 0.01, "win"),
            _make_analytics_row(0.78, "-20.00", -0.01, "loss"),
        ]

        await recompute_calibration_for_strategy(
            "rsi_agent", rows, cal_store, ConfidenceCalibrationConfig(), windows=["all"]
        )

        result = await cal_store.get("rsi_agent", "0.70-0.80", "all")
        assert result is not None
        assert result["trade_count"] == 3
        assert result["win_rate"] == pytest.approx(2 / 3)

    async def test_none_confidence_goes_to_unknown_bucket(self, cal_store: ConfidenceCalibrationStore):
        rows = [
            _make_analytics_row(None, "10.00", 0.005, "win"),
            _make_analytics_row(None, "-5.00", -0.002, "loss"),
        ]

        await recompute_calibration_for_strategy(
            "rsi_agent", rows, cal_store, ConfidenceCalibrationConfig(), windows=["all"]
        )

        result = await cal_store.get("rsi_agent", "unknown", "all")
        assert result is not None
        assert result["trade_count"] == 2

    async def test_multiple_windows(self, cal_store: ConfidenceCalibrationStore):
        rows = [
            _make_analytics_row(0.75, "50.00", 0.02, "win", "2026-03-01T10:00:00"),
            _make_analytics_row(0.75, "30.00", 0.01, "win", "2026-03-25T10:00:00"),
        ]

        await recompute_calibration_for_strategy(
            "rsi_agent", rows, cal_store, ConfidenceCalibrationConfig(), windows=["30d", "all"]
        )

        all_result = await cal_store.get("rsi_agent", "0.70-0.80", "all")
        assert all_result["trade_count"] == 2

        # 30d window includes only the recent trade (2026-03-25 is within 30d of 2026-03-31)
        result_30d = await cal_store.get("rsi_agent", "0.70-0.80", "30d")
        assert result_30d is not None
        assert result_30d["trade_count"] >= 1

    async def test_multiple_buckets(self, cal_store: ConfidenceCalibrationStore):
        rows = [
            _make_analytics_row(0.65, "10.00", 0.005, "win"),
            _make_analytics_row(0.75, "20.00", 0.010, "win"),
            _make_analytics_row(0.85, "30.00", 0.015, "win"),
        ]

        await recompute_calibration_for_strategy(
            "rsi_agent", rows, cal_store, ConfidenceCalibrationConfig(), windows=["all"]
        )

        r60 = await cal_store.get("rsi_agent", "0.60-0.70", "all")
        r70 = await cal_store.get("rsi_agent", "0.70-0.80", "all")
        r80 = await cal_store.get("rsi_agent", "0.80-0.90", "all")

        assert r60 is not None and r60["trade_count"] == 1
        assert r70 is not None and r70["trade_count"] == 1
        assert r80 is not None and r80["trade_count"] == 1

    async def test_sample_quality_in_summary(self, cal_store: ConfidenceCalibrationStore):
        # 5 trades → insufficient
        rows = [_make_analytics_row(0.75, "10.00", 0.005, "win") for _ in range(5)]
        await recompute_calibration_for_strategy(
            "rsi_agent", rows, cal_store, ConfidenceCalibrationConfig(), windows=["all"]
        )
        result = await cal_store.get("rsi_agent", "0.70-0.80", "all")
        assert result["sample_quality"] == "insufficient"

    async def test_idempotent_recompute(self, cal_store: ConfidenceCalibrationStore):
        rows = [_make_analytics_row(0.75, "50.00", 0.02, "win") for _ in range(30)]

        await recompute_calibration_for_strategy(
            "rsi_agent", rows, cal_store, ConfidenceCalibrationConfig(), windows=["all"]
        )
        await recompute_calibration_for_strategy(
            "rsi_agent", rows, cal_store, ConfidenceCalibrationConfig(), windows=["all"]
        )

        all_rows = await cal_store.list_all()
        assert len(all_rows) == 1
        assert all_rows[0]["trade_count"] == 30
