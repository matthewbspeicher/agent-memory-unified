from __future__ import annotations

from __future__ import annotations

import logging
from typing import Any

from competition.models import XpSource

logger = logging.getLogger(__name__)


async def award_arena_completion_rewards(
    store: Any,
    competitor_id: str,
    asset: str,
    session_data: dict,
    challenge_data: dict,
) -> dict:
    xp_awarded = 0
    bonus_xp = 0

    score = session_data.get("score", 0)
    turn_count = session_data.get("turn_count", 0)
    max_turns = challenge_data.get("max_turns", 10)
    base_xp = challenge_data.get("xp_reward", 50)

    if score > 0:
        xp_amount = int(base_xp * (score / 100))
        xp_amount = max(xp_amount, 10)

        try:
            await store.award_xp(
                competitor_id=competitor_id,
                asset=asset,
                source=XpSource.MISSION_COMPLETE,
                amount=xp_amount,
            )
            xp_awarded = xp_amount
        except Exception as e:
            logger.error(f"Failed to award XP: {e}")

    efficiency = 1.0 - (turn_count / max_turns) if max_turns > 0 else 0
    if efficiency >= 0.5:
        bonus = int(base_xp * 0.25)
        try:
            await store.award_xp(
                competitor_id=competitor_id,
                asset=asset,
                source=XpSource.STREAK_MILESTONE,
                amount=bonus,
            )
            bonus_xp = bonus
        except Exception as e:
            logger.error(f"Failed to award bonus XP: {e}")

    return {
        "xp_awarded": xp_awarded,
        "bonus_xp": bonus_xp,
        "total_xp": xp_awarded + bonus_xp,
    }


def get_arena_achievement_checks(
    session_data: dict,
    challenge_data: dict,
    competitor_stats: dict | None = None,
) -> list[dict]:
    achievements = []
    score = session_data.get("score", 0)
    difficulty = challenge_data.get("difficulty", 1)
    turn_count = session_data.get("turn_count", 0)
    room_type = challenge_data.get("room_type", "")

    if competitor_stats and competitor_stats.get("sessions_completed", 0) == 0:
        achievements.append(
            {
                "id": "arena_first_clear",
                "name": "First Blood",
                "description": "Complete your first arena challenge",
                "xp_reward": 50,
            }
        )

    if score >= 100:
        achievements.append(
            {
                "id": "arena_perfect",
                "name": "Perfect Run",
                "description": "Achieve a perfect score in an arena challenge",
                "xp_reward": 100,
            }
        )

    max_turns = challenge_data.get("max_turns", 10)
    if turn_count <= max_turns * 0.25:
        achievements.append(
            {
                "id": "arena_speed_demon",
                "name": "Speed Demon",
                "description": "Complete a challenge with exceptional speed",
                "xp_reward": 75,
            }
        )

    if room_type and competitor_stats:
        completed_types = competitor_stats.get("completed_room_types", set())
        if isinstance(completed_types, list):
            completed_types = set(completed_types)
        completed_types.add(room_type)
        if len(completed_types) >= 3:
            achievements.append(
                {
                    "id": "arena_master_all",
                    "name": "Jack of All Trades",
                    "description": "Complete challenges of all room types",
                    "xp_reward": 150,
                }
            )

    if difficulty >= 4:
        achievements.append(
            {
                "id": "arena_hard_mode",
                "name": "Hard Mode",
                "description": "Complete a high-difficulty challenge",
                "xp_reward": 100,
            }
        )

    return achievements
