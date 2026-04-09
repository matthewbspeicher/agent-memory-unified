"""
Achievements API routes.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

from api.deps import verify_api_key
from achievements import create_tracker, get_all_achievements, ACHIEVEMENTS


router = APIRouter(
    prefix="/achievements",
    tags=["achievements"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("")
async def get_all():
    """Get all achievements with their status."""
    all_achievements = get_all_achievements()
    tracker = create_tracker()
    unlocked_ids = tracker.get_unlocked_ids()

    return {
        "achievements": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "icon": a.icon,
                "category": a.category.value,
                "xp_reward": a.xp_reward,
                "rarity": a.rarity,
                "unlocked": a.id in unlocked_ids,
            }
            for a in all_achievements.values()
        ],
        "total_xp": tracker.get_xp(),
    }


@router.get("/me")
async def get_my_achievements():
    """Get current user's achievements (placeholder for multi-user)."""
    tracker = create_tracker()
    unlocked = tracker.get_unlocked()

    return {
        "unlocked": [
            {
                "id": u.achievement_id,
                "unlocked_at": u.unlocked_at.isoformat(),
            }
            for u in unlocked
        ],
        "xp": tracker.get_xp(),
    }


@router.get("/{achievement_id}")
async def get_achievement(achievement_id: str):
    """Get a specific achievement."""
    from achievements.registry import get_achievement

    achievement = get_achievement(achievement_id)
    if not achievement:
        raise HTTPException(status_code=404, detail="Achievement not found")

    tracker = create_tracker()
    is_unlocked = tracker.is_unlocked(achievement_id)

    return {
        "id": achievement.id,
        "name": achievement.name,
        "description": achievement.description,
        "icon": achievement.icon,
        "category": achievement.category.value,
        "xp_reward": achievement.xp_reward,
        "rarity": achievement.rarity,
        "unlocked": is_unlocked,
    }


@router.post("/{achievement_id}/unlock")
async def unlock_achievement(achievement_id: str, context: Optional[dict] = None):
    """Manually unlock an achievement (admin/debug)."""
    from achievements.registry import get_achievement

    achievement = get_achievement(achievement_id)
    if not achievement:
        raise HTTPException(status_code=404, detail="Achievement not found")

    tracker = create_tracker()
    success = tracker.unlock_specific(achievement_id, context or {})

    if success:
        return {"message": f"Unlocked {achievement_id}", "xp": tracker.get_xp()}
    return {"message": f"{achievement_id} already unlocked", "xp": tracker.get_xp()}
