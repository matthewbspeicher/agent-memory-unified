# tests/unit/competition/test_engine.py
from __future__ import annotations

import pytest
from competition.engine import (
    calculate_elo_delta,
    expected_score,
    k_factor_for_confidence,
    k_factor_for_new_competitor,
)


class TestExpectedScore:
    def test_equal_ratings(self):
        assert expected_score(1000, 1000) == pytest.approx(0.5)

    def test_higher_rated_favored(self):
        score = expected_score(1400, 1000)
        assert score > 0.9

    def test_lower_rated_underdog(self):
        score = expected_score(1000, 1400)
        assert score < 0.1

    def test_symmetry(self):
        a = expected_score(1200, 1000)
        b = expected_score(1000, 1200)
        assert a + b == pytest.approx(1.0)


class TestCalculateEloDelta:
    def test_win_equal_ratings(self):
        delta = calculate_elo_delta(
            rating=1000, opponent_rating=1000, outcome=1.0, k=20
        )
        assert delta == 10  # K * (1 - 0.5) = 10

    def test_loss_equal_ratings(self):
        delta = calculate_elo_delta(
            rating=1000, opponent_rating=1000, outcome=0.0, k=20
        )
        assert delta == -10

    def test_draw_equal_ratings(self):
        delta = calculate_elo_delta(
            rating=1000, opponent_rating=1000, outcome=0.5, k=20
        )
        assert delta == 0

    def test_upset_win_big_delta(self):
        # Low-rated beats high-rated: big gain
        delta = calculate_elo_delta(rating=800, opponent_rating=1200, outcome=1.0, k=20)
        assert delta > 15

    def test_expected_win_small_delta(self):
        # High-rated beats low-rated: small gain
        delta = calculate_elo_delta(rating=1200, opponent_rating=800, outcome=1.0, k=20)
        assert delta < 5

    def test_custom_k_factor(self):
        delta_low = calculate_elo_delta(1000, 1000, 1.0, k=10)
        delta_high = calculate_elo_delta(1000, 1000, 1.0, k=40)
        assert delta_high == delta_low * 4


class TestKFactorForConfidence:
    def test_high_confidence(self):
        assert k_factor_for_confidence(0.9) == 40

    def test_medium_confidence(self):
        assert k_factor_for_confidence(0.6) == 20

    def test_low_confidence(self):
        assert k_factor_for_confidence(0.3) == 10

    def test_boundary_high(self):
        assert k_factor_for_confidence(0.8) == 40

    def test_boundary_medium(self):
        assert k_factor_for_confidence(0.5) == 20


class TestKFactorForNewCompetitor:
    def test_first_match(self):
        assert k_factor_for_new_competitor(0) == 40

    def test_ninth_match(self):
        assert k_factor_for_new_competitor(9) == 40

    def test_eleventh_match(self):
        assert k_factor_for_new_competitor(11) == 20
