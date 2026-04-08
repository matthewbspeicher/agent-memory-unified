# tests/unit/competition/test_achievements.py
from __future__ import annotations

import pytest
from competition.achievements import (
    AchievementChecker,
    AchievementProgress,
    AchievementType,
    CompetitorState,
)


class TestAchievementChecker:
    def test_streak_5_not_met(self):
        checker = AchievementChecker()
        state = CompetitorState(
            current_streak=4, sharpe_7d=0.5, tier="silver", diamond_days_30d=0
        )
        result = checker.check(AchievementType.STREAK_5, state)
        assert result.earned is False
        assert result.progress == pytest.approx(4 / 5)

    def test_streak_5_met(self):
        checker = AchievementChecker()
        state = CompetitorState(
            current_streak=5, sharpe_7d=0.5, tier="silver", diamond_days_30d=0
        )
        result = checker.check(AchievementType.STREAK_5, state)
        assert result.earned is True

    def test_streak_10_met(self):
        checker = AchievementChecker()
        state = CompetitorState(
            current_streak=10, sharpe_7d=0.5, tier="silver", diamond_days_30d=0
        )
        result = checker.check(AchievementType.STREAK_10, state)
        assert result.earned is True

    def test_sharp_shooter_not_enough_signals(self):
        checker = AchievementChecker()
        state = CompetitorState(
            current_streak=0,
            sharpe_7d=3.0,
            tier="silver",
            diamond_days_30d=0,
            signal_count_7d=5,
        )
        result = checker.check(AchievementType.SHARP_SHOOTER, state)
        assert result.earned is False  # Need 10+ signals

    def test_sharp_shooter_met(self):
        checker = AchievementChecker()
        state = CompetitorState(
            current_streak=0,
            sharpe_7d=2.5,
            tier="gold",
            diamond_days_30d=0,
            signal_count_7d=15,
        )
        result = checker.check(AchievementType.SHARP_SHOOTER, state)
        assert result.earned is True

    def test_iron_throne_progress(self):
        checker = AchievementChecker()
        state = CompetitorState(
            current_streak=0, sharpe_7d=1.0, tier="diamond", diamond_days_30d=20
        )
        result = checker.check(AchievementType.IRON_THRONE, state)
        assert result.earned is False  # Need 30 days
        assert result.progress == pytest.approx(20 / 30)

    def test_iron_throne_met(self):
        checker = AchievementChecker()
        state = CompetitorState(
            current_streak=0, sharpe_7d=1.0, tier="diamond", diamond_days_30d=30
        )
        result = checker.check(AchievementType.IRON_THRONE, state)
        assert result.earned is True

    def test_all_achievements_return_progress(self):
        checker = AchievementChecker()
        state = CompetitorState(
            current_streak=3,
            sharpe_7d=1.5,
            tier="gold",
            diamond_days_30d=10,
            signal_count_7d=20,
        )
        for atype in AchievementType:
            result = checker.check(atype, state)
            assert 0.0 <= result.progress <= 1.0
