from datetime import datetime, timezone

from achievements.registry import (
    ACHIEVEMENTS,
    AchievementCategory,
    get_achievement,
    get_all_achievements,
    get_achievements_by_category,
)
from achievements.tracker import (
    AchievementTracker,
    UnlockedAchievement,
    AchievementProgress,
    create_tracker,
)


class TestAchievementRegistry:
    def test_all_achievements_registered(self):
        assert len(ACHIEVEMENTS) > 0, "Should have at least one achievement"

    def test_get_achievement_exists(self):
        achievement = get_achievement("first_trade")
        assert achievement is not None
        assert achievement.id == "first_trade"

    def test_get_achievement_not_found(self):
        achievement = get_achievement("nonexistent")
        assert achievement is None

    def test_get_all_achievements(self):
        all_achievements = get_all_achievements()
        assert len(all_achievements) == len(ACHIEVEMENTS)
        assert all(a_id in ACHIEVEMENTS for a_id in all_achievements.keys())

    def test_get_achievements_by_category(self):
        trading = get_achievements_by_category(AchievementCategory.TRADING)
        assert len(trading) > 0
        assert all(a.category == AchievementCategory.TRADING for a in trading)


class TestAchievementTracker:
    def test_tracker_creation(self):
        tracker = AchievementTracker(user_id="test_user")
        assert tracker._user_id == "test_user"
        assert len(tracker._unlocked) == 0
        assert len(tracker._progress) == 0

    def test_create_tracker_factory(self):
        tracker = create_tracker()
        assert isinstance(tracker, AchievementTracker)
        assert tracker._user_id == "default"

    def test_check_and_update_first_trade(self):
        tracker = AchievementTracker()
        context = {"total_trades": 1}
        unlocked = tracker.check_and_update(context)
        assert len(unlocked) >= 1
        assert "first_trade" in [u.id for u in unlocked]

    def test_check_and_update_no_trades(self):
        tracker = AchievementTracker()
        context = {"total_trades": 0}
        unlocked = tracker.check_and_update(context)
        assert len(unlocked) == 0

    def test_check_and_update_ten_trades(self):
        tracker = AchievementTracker()
        context = {"total_trades": 10}
        unlocked = tracker.check_and_update(context)
        unlocked_ids = [u.id for u in unlocked]
        assert "first_trade" in unlocked_ids
        assert "ten_bagger" in unlocked_ids

    def test_already_unlocked_not_rechecked(self):
        tracker = AchievementTracker()
        context = {"total_trades": 1}
        unlocked1 = tracker.check_and_update(context)
        assert len(unlocked1) >= 1

        context2 = {"total_trades": 50}
        unlocked2 = tracker.check_and_update(context2)
        assert "first_trade" not in [u.id for u in unlocked2]

    def test_get_progress_not_started(self):
        tracker = AchievementTracker()
        progress = tracker.get_all_progress()
        first_trade_progress = next(
            (p for p in progress if p.achievement_id == "first_trade"), None
        )
        assert first_trade_progress is not None
        assert first_trade_progress.unlocked is False

    def test_get_progress_after_unlock(self):
        tracker = AchievementTracker()
        tracker.check_and_update({"total_trades": 1})
        progress = tracker.get_progress("first_trade")
        assert progress is not None
        assert progress.unlocked is True
        assert progress.unlocked_at is not None

    def test_get_unlocked_achievements(self):
        tracker = AchievementTracker()
        tracker.check_and_update({"total_trades": 1})
        unlocked = tracker.get_unlocked()
        assert len(unlocked) >= 1

    def test_profit_achievements(self):
        tracker = AchievementTracker()
        context = {"consecutive_profitable_days": 5}
        unlocked = tracker.check_and_update(context)
        unlocked_ids = [u.id for u in unlocked]
        assert "streak_3" in unlocked_ids

    def test_win_rate_achievements(self):
        tracker = AchievementTracker()
        context = {"win_rate": 0.75}
        unlocked = tracker.check_and_update(context)
        unlocked_ids = [u.id for u in unlocked]
        assert "win_rate_70" in unlocked_ids

    def test_sharpe_achievement(self):
        tracker = AchievementTracker()
        context = {"is_best_sharpe_this_month": True}
        unlocked = tracker.check_and_update(context)
        unlocked_ids = [u.id for u in unlocked]
        assert "sharpe_king" in unlocked_ids

    def test_consecutive_wins_achievement(self):
        tracker = AchievementTracker()
        context = {"consecutive_profitable_days": 10}
        unlocked = tracker.check_and_update(context)
        unlocked_ids = [u.id for u in unlocked]
        assert "streak_10" in unlocked_ids

    def test_hold_duration_achievement(self):
        tracker = AchievementTracker()
        context = {"held_position_24h_5pct": True}
        unlocked = tracker.check_and_update(context)
        unlocked_ids = [u.id for u in unlocked]
        assert "diamond_hands" in unlocked_ids


class TestUnlockedAchievement:
    def test_default_unlocked_at(self):
        unlocked = UnlockedAchievement(achievement_id="test")
        assert unlocked.unlocked_at is not None
        assert unlocked.unlocked_at.tzinfo is not None

    def test_custom_unlocked_at(self):
        custom_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        unlocked = UnlockedAchievement(achievement_id="test", unlocked_at=custom_time)
        assert unlocked.unlocked_at == custom_time


class TestAchievementProgress:
    def test_default_values(self):
        progress = AchievementProgress(achievement_id="test")
        assert progress.achievement_id == "test"
        assert progress.current_value == 0.0
        assert progress.target_value == 0.0
        assert progress.unlocked is False
        assert progress.unlocked_at is None
