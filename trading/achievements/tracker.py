"""
Achievement tracker - monitors and unlocks achievements based on trading activity.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from achievements.registry import (
    ACHIEVEMENTS,
    AchievementDefinition,
    get_achievement,
)


@dataclass
class UnlockedAchievement:
    """An achievement that has been unlocked."""

    achievement_id: str
    unlocked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AchievementProgress:
    """Tracks progress toward an achievement."""

    achievement_id: str
    current_value: float = 0.0
    target_value: float = 0.0
    unlocked: bool = False
    unlocked_at: datetime | None = None


class AchievementTracker:
    """Tracks achievement progress and unlocks."""

    def __init__(self, user_id: str = "default"):
        self._user_id = user_id
        self._unlocked: dict[str, UnlockedAchievement] = {}
        self._progress: dict[str, AchievementProgress] = {}

    def check_and_update(self, context: dict[str, Any]) -> list[AchievementDefinition]:
        """
        Check all achievements against context and unlock any that meet criteria.
        Returns list of newly unlocked achievements.
        """
        newly_unlocked = []

        for achievement_id, definition in ACHIEVEMENTS.items():
            if achievement_id in self._unlocked:
                continue

            if definition.criteria_fn(context):
                self._unlocked[achievement_id] = UnlockedAchievement(
                    achievement_id=achievement_id,
                    context=context,
                )
                self._progress[achievement_id] = AchievementProgress(
                    achievement_id=achievement_id,
                    unlocked=True,
                    unlocked_at=datetime.now(timezone.utc),
                )
                newly_unlocked.append(definition)

        return newly_unlocked

    def unlock_specific(
        self, achievement_id: str, context: dict[str, Any] = None
    ) -> bool:
        """Manually unlock a specific achievement."""
        if achievement_id in self._unlocked:
            return False

        definition = get_achievement(achievement_id)
        if not definition:
            return False

        self._unlocked[achievement_id] = UnlockedAchievement(
            achievement_id=achievement_id,
            context=context or {},
        )
        self._progress[achievement_id] = AchievementProgress(
            achievement_id=achievement_id,
            unlocked=True,
            unlocked_at=datetime.now(timezone.utc),
        )
        return True

    def get_unlocked(self) -> list[UnlockedAchievement]:
        """Get all unlocked achievements."""
        return list(self._unlocked.values())

    def get_unlocked_ids(self) -> list[str]:
        """Get list of unlocked achievement IDs."""
        return list(self._unlocked.keys())

    def is_unlocked(self, achievement_id: str) -> bool:
        """Check if an achievement is unlocked."""
        return achievement_id in self._unlocked

    def get_progress(self, achievement_id: str) -> AchievementProgress | None:
        """Get progress for a specific achievement."""
        return self._progress.get(achievement_id)

    def get_all_progress(self) -> list[AchievementProgress]:
        """Get progress for all achievements."""
        result = []
        for achievement_id, definition in ACHIEVEMENTS.items():
            if achievement_id in self._progress:
                result.append(self._progress[achievement_id])
            else:
                result.append(AchievementProgress(achievement_id=achievement_id))
        return result

    def get_xp(self) -> int:
        """Calculate total XP from unlocked achievements."""
        total = 0
        for achievement_id in self._unlocked.keys():
            definition = get_achievement(achievement_id)
            if definition:
                total += definition.xp_reward
        return total

    def reset(self):
        """Reset all progress (for testing)."""
        self._unlocked.clear()
        self._progress.clear()


def create_tracker(user_id: str = "default") -> AchievementTracker:
    """Factory function to create a tracker."""
    return AchievementTracker(user_id=user_id)
