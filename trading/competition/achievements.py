# trading/competition/achievements.py
"""Event-driven achievement system for competitors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AchievementType(str, Enum):
    STREAK_5 = "streak_5"
    STREAK_10 = "streak_10"
    SHARP_SHOOTER = "sharp_shooter"
    IRON_THRONE = "iron_throne"
    COMEBACK_KID = "comeback_kid"
    REGIME_SURVIVOR = "regime_survivor"
    WHALE_WHISPERER = "whale_whisperer"
    FIRST_BLOOD = "first_blood"


ACHIEVEMENT_CONFIG = {
    AchievementType.STREAK_5: {"icon": "🔥", "label": "Hot Streak", "rarity": "common"},
    AchievementType.STREAK_10: {
        "icon": "🔥",
        "label": "Blazing Streak",
        "rarity": "rare",
    },
    AchievementType.SHARP_SHOOTER: {
        "icon": "🎯",
        "label": "Sharp Shooter",
        "rarity": "rare",
    },
    AchievementType.IRON_THRONE: {
        "icon": "💎",
        "label": "Iron Throne",
        "rarity": "legendary",
    },
    AchievementType.COMEBACK_KID: {
        "icon": "⬆️",
        "label": "Comeback Kid",
        "rarity": "legendary",
    },
    AchievementType.REGIME_SURVIVOR: {
        "icon": "🐂",
        "label": "Regime Survivor",
        "rarity": "rare",
    },
    AchievementType.WHALE_WHISPERER: {
        "icon": "🐋",
        "label": "Whale Whisperer",
        "rarity": "rare",
    },
    AchievementType.FIRST_BLOOD: {
        "icon": "⚡",
        "label": "First Blood",
        "rarity": "rare",
    },
}


@dataclass
class CompetitorState:
    current_streak: int = 0
    sharpe_7d: float = 0.0
    tier: str = "silver"
    diamond_days_30d: int = 0
    signal_count_7d: int = 0
    promoted_from_bronze_to_gold: bool = False
    survived_regime_change: bool = False
    whale_correct: bool = False
    was_first_signal: bool = False


@dataclass
class AchievementProgress:
    achievement_type: AchievementType
    earned: bool
    progress: float  # 0.0 to 1.0
    current_value: float = 0
    target_value: float = 1


class AchievementChecker:
    """Checks all achievement conditions against competitor state."""

    def check(
        self, atype: AchievementType, state: CompetitorState
    ) -> AchievementProgress:
        """Check if an achievement is earned and calculate progress."""
        checkers = {
            AchievementType.STREAK_5: self._check_streak_5,
            AchievementType.STREAK_10: self._check_streak_10,
            AchievementType.SHARP_SHOOTER: self._check_sharp_shooter,
            AchievementType.IRON_THRONE: self._check_iron_throne,
            AchievementType.COMEBACK_KID: self._check_comeback_kid,
            AchievementType.REGIME_SURVIVOR: self._check_regime_survivor,
            AchievementType.WHALE_WHISPERER: self._check_whale_whisperer,
            AchievementType.FIRST_BLOOD: self._check_first_blood,
        }
        return checkers[atype](state)

    def check_all(self, state: CompetitorState) -> list[AchievementProgress]:
        return [self.check(atype, state) for atype in AchievementType]

    def _check_streak_5(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.STREAK_5,
            earned=state.current_streak >= 5,
            progress=min(state.current_streak / 5, 1.0),
            current_value=state.current_streak,
            target_value=5,
        )

    def _check_streak_10(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.STREAK_10,
            earned=state.current_streak >= 10,
            progress=min(state.current_streak / 10, 1.0),
            current_value=state.current_streak,
            target_value=10,
        )

    def _check_sharp_shooter(self, state: CompetitorState) -> AchievementProgress:
        earned = state.sharpe_7d >= 2.0 and state.signal_count_7d >= 10
        progress = (
            min(state.sharpe_7d / 2.0, 1.0) if state.signal_count_7d >= 10 else 0.0
        )
        return AchievementProgress(
            AchievementType.SHARP_SHOOTER,
            earned=earned,
            progress=progress,
            current_value=state.sharpe_7d,
            target_value=2.0,
        )

    def _check_iron_throne(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.IRON_THRONE,
            earned=state.diamond_days_30d >= 30,
            progress=min(state.diamond_days_30d / 30, 1.0),
            current_value=state.diamond_days_30d,
            target_value=30,
        )

    def _check_comeback_kid(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.COMEBACK_KID,
            earned=state.promoted_from_bronze_to_gold,
            progress=1.0 if state.promoted_from_bronze_to_gold else 0.0,
        )

    def _check_regime_survivor(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.REGIME_SURVIVOR,
            earned=state.survived_regime_change,
            progress=1.0 if state.survived_regime_change else 0.0,
        )

    def _check_whale_whisperer(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.WHALE_WHISPERER,
            earned=state.whale_correct,
            progress=1.0 if state.whale_correct else 0.0,
        )

    def _check_first_blood(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.FIRST_BLOOD,
            earned=state.was_first_signal,
            progress=1.0 if state.was_first_signal else 0.0,
        )
