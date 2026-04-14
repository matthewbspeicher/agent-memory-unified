"""
Achievement tracker - monitors and unlocks achievements based on trading activity.
Supports optional DB persistence for per-agent achievement state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING
import json
import logging

from achievements.registry import (
    ACHIEVEMENTS,
    AchievementDefinition,
    get_achievement,
)

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)


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
    """Tracks achievement progress and unlocks. Optionally persists to DB."""

    def __init__(
        self, user_id: str = "default", db: "aiosqlite.Connection | None" = None
    ):
        self._user_id = user_id
        self._db = db
        self._unlocked: dict[str, UnlockedAchievement] = {}
        self._progress: dict[str, AchievementProgress] = {}
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        """Load unlocked achievements from DB on first access."""
        if self._loaded or not self._db:
            self._loaded = True
            return

        try:
            cursor = await self._db.execute(
                """SELECT achievement_id, unlocked_at, context
                   FROM agent_achievements
                   WHERE agent_name = ?
                   ORDER BY unlocked_at DESC""",
                (self._user_id,),
            )
            rows = await cursor.fetchall()
            for row in rows:
                achievement_id = row[0]
                unlocked_at = (
                    datetime.fromisoformat(row[1])
                    if row[1]
                    else datetime.now(timezone.utc)
                )
                context = json.loads(row[2]) if row[2] else {}

                self._unlocked[achievement_id] = UnlockedAchievement(
                    achievement_id=achievement_id,
                    unlocked_at=unlocked_at,
                    context=context,
                )
                self._progress[achievement_id] = AchievementProgress(
                    achievement_id=achievement_id,
                    unlocked=True,
                    unlocked_at=unlocked_at,
                )
            logger.debug(
                "Loaded %d achievements for %s", len(self._unlocked), self._user_id
            )
        except Exception as exc:
            logger.warning("Failed to load achievements for %s: %s", self._user_id, exc)
        finally:
            self._loaded = True

    async def _persist(self, achievement_id: str, context: dict[str, Any]) -> None:
        """Save a single achievement unlock to DB."""
        if not self._db:
            return

        try:
            await self._db.execute(
                """INSERT OR IGNORE INTO agent_achievements (agent_name, achievement_id, context)
                   VALUES (?, ?, ?)""",
                (self._user_id, achievement_id, json.dumps(context)),
            )
            await self._db.commit()
        except Exception as exc:
            logger.warning(
                "Failed to persist achievement %s for %s: %s",
                achievement_id,
                self._user_id,
                exc,
            )

    async def check_and_update(
        self, context: dict[str, Any]
    ) -> list[AchievementDefinition]:
        """
        Check all achievements against context and unlock any that meet criteria.
        Returns list of newly unlocked achievements.
        """
        await self._ensure_loaded()
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
                await self._persist(achievement_id, context)

        return newly_unlocked

    async def unlock_specific(
        self, achievement_id: str, context: dict[str, Any] = None
    ) -> bool:
        """Manually unlock a specific achievement."""
        await self._ensure_loaded()

        if achievement_id in self._unlocked:
            return False

        definition = get_achievement(achievement_id)
        if not definition:
            return False

        ctx = context or {}
        self._unlocked[achievement_id] = UnlockedAchievement(
            achievement_id=achievement_id,
            context=ctx,
        )
        self._progress[achievement_id] = AchievementProgress(
            achievement_id=achievement_id,
            unlocked=True,
            unlocked_at=datetime.now(timezone.utc),
        )
        await self._persist(achievement_id, ctx)
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

    async def load(self) -> None:
        """Explicitly load achievements from DB. Call before using sync methods."""
        await self._ensure_loaded()

    def reset(self):
        """Reset all progress (for testing)."""
        self._unlocked.clear()
        self._progress.clear()
        self._loaded = False


def create_tracker(user_id: str = "default", db=None) -> AchievementTracker:
    """Factory function to create a tracker. Optionally accepts DB for persistence."""
    return AchievementTracker(user_id=user_id, db=db)
