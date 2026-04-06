"""Unit tests for Bittensor miner ranking computation."""

from __future__ import annotations

from integrations.bittensor.models import (
    MinerRankingInput,
    RankingWeights,
    RankingConfig,
)


class TestMinerRankingInput:
    def test_create_with_all_fields(self):
        inp = MinerRankingInput(
            miner_hotkey="5Fhot1",
            windows_evaluated=50,
            direction_accuracy=0.7,
            mean_magnitude_error=0.03,
            mean_path_correlation=0.5,
            raw_incentive_score=0.8,
        )
        assert inp.miner_hotkey == "5Fhot1"
        assert inp.windows_evaluated == 50
        assert inp.mean_path_correlation == 0.5

    def test_create_with_none_path_correlation(self):
        inp = MinerRankingInput(
            miner_hotkey="5Fhot2",
            windows_evaluated=5,
            direction_accuracy=0.6,
            mean_magnitude_error=0.05,
            mean_path_correlation=None,
            raw_incentive_score=0.3,
        )
        assert inp.mean_path_correlation is None


class TestRankingWeights:
    def test_direction_heavy(self):
        w = RankingWeights(direction=0.60, magnitude=0.25, path=0.15)
        assert abs(w.direction + w.magnitude + w.path - 1.0) < 1e-9

    def test_return_sensitive(self):
        w = RankingWeights(direction=0.45, magnitude=0.35, path=0.20)
        assert abs(w.direction + w.magnitude + w.path - 1.0) < 1e-9


class TestRankingConfig:
    def test_defaults(self):
        cfg = RankingConfig(
            min_windows_for_ranking=20,
            alpha_decay_per_window=0.003,
            alpha_floor=0.1,
            lookback_windows=500,
        )
        assert cfg.alpha_floor == 0.1


from datetime import datetime

from integrations.bittensor.ranking import (
    compute_rankings,
    DIRECTION_HEAVY,
    RETURN_SENSITIVE,
)
from integrations.bittensor.models import MinerRanking


def _make_input(
    hotkey="5Fhot1",
    windows=50,
    dir_acc=0.7,
    mag_err=0.03,
    path_corr=0.5,
    incentive=0.8,
):
    return MinerRankingInput(
        miner_hotkey=hotkey,
        windows_evaluated=windows,
        direction_accuracy=dir_acc,
        mean_magnitude_error=mag_err,
        mean_path_correlation=path_corr,
        raw_incentive_score=incentive,
    )


def _default_config():
    return RankingConfig(
        min_windows_for_ranking=20,
        alpha_decay_per_window=0.003,
        alpha_floor=0.1,
        lookback_windows=500,
    )


def _fixed_now() -> datetime:
    return datetime(2026, 3, 31, 12, 0, 0)


class TestComputeRankings:
    def test_empty_inputs_returns_empty(self):
        result = compute_rankings([], DIRECTION_HEAVY, _default_config(), _fixed_now())
        assert result == []

    def test_single_miner_returns_one_ranking(self):
        inputs = [_make_input()]
        results = compute_rankings(
            inputs, DIRECTION_HEAVY, _default_config(), _fixed_now()
        )
        assert len(results) == 1
        assert isinstance(results[0], MinerRanking)
        assert results[0].miner_hotkey == "5Fhot1"

    def test_single_miner_degenerate_normalization(self):
        inputs = [_make_input(windows=50, dir_acc=0.7, mag_err=0.03, incentive=0.9)]
        results = compute_rankings(
            inputs, DIRECTION_HEAVY, _default_config(), _fixed_now()
        )
        r = results[0]
        assert r.latest_incentive_score == 0.9
        assert r.windows_evaluated == 50

    def test_alpha_is_1_before_min_windows(self):
        inputs = [_make_input(windows=10, incentive=0.8)]
        results = compute_rankings(
            inputs, DIRECTION_HEAVY, _default_config(), _fixed_now()
        )
        r = results[0]
        assert r.alpha_used == 1.0
        assert abs(r.hybrid_score - 0.5) < 1e-9

    def test_alpha_decays_after_min_windows(self):
        cfg = _default_config()
        inputs = [_make_input(windows=120)]
        results = compute_rankings(inputs, DIRECTION_HEAVY, cfg, _fixed_now())
        r = results[0]
        assert abs(r.alpha_used - 0.7) < 1e-9

    def test_alpha_floor(self):
        cfg = _default_config()
        inputs = [_make_input(windows=1000)]
        results = compute_rankings(inputs, DIRECTION_HEAVY, cfg, _fixed_now())
        assert results[0].alpha_used == cfg.alpha_floor

    def test_two_miners_different_scores(self):
        inputs = [
            _make_input(
                hotkey="good", dir_acc=0.9, mag_err=0.01, path_corr=0.8, incentive=0.7
            ),
            _make_input(
                hotkey="bad", dir_acc=0.3, mag_err=0.10, path_corr=-0.2, incentive=0.3
            ),
        ]
        results = compute_rankings(
            inputs, DIRECTION_HEAVY, _default_config(), _fixed_now()
        )
        by_key = {r.miner_hotkey: r for r in results}
        assert by_key["good"].hybrid_score > by_key["bad"].hybrid_score

    def test_nullable_path_correlation_redistributes_weights(self):
        inputs = [_make_input(path_corr=None)]
        results = compute_rankings(
            inputs, DIRECTION_HEAVY, _default_config(), _fixed_now()
        )
        assert len(results) == 1
        assert 0.0 <= results[0].internal_score <= 1.0

    def test_all_equal_incentives_get_0_5(self):
        inputs = [
            _make_input(hotkey="a", incentive=0.5),
            _make_input(hotkey="b", incentive=0.5),
        ]
        results = compute_rankings(
            inputs, DIRECTION_HEAVY, _default_config(), _fixed_now()
        )
        assert results[0].hybrid_score == results[1].hybrid_score

    def test_all_equal_magnitude_errors_get_0_5(self):
        inputs = [
            _make_input(hotkey="a", mag_err=0.05, incentive=0.6),
            _make_input(hotkey="b", mag_err=0.05, incentive=0.4),
        ]
        results = compute_rankings(
            inputs, DIRECTION_HEAVY, _default_config(), _fixed_now()
        )
        by_key = {r.miner_hotkey: r for r in results}
        assert by_key["a"].internal_score == by_key["b"].internal_score

    def test_weight_profiles_are_valid(self):
        assert (
            abs(
                DIRECTION_HEAVY.direction
                + DIRECTION_HEAVY.magnitude
                + DIRECTION_HEAVY.path
                - 1.0
            )
            < 1e-9
        )
        assert (
            abs(
                RETURN_SENSITIVE.direction
                + RETURN_SENSITIVE.magnitude
                + RETURN_SENSITIVE.path
                - 1.0
            )
            < 1e-9
        )

    def test_updated_at_is_set(self):
        inputs = [_make_input()]
        now = _fixed_now()
        results = compute_rankings(inputs, DIRECTION_HEAVY, _default_config(), now)
        assert results[0].updated_at == now
