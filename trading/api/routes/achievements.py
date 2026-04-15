"""
Achievements API routes.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional

from api.auth import verify_api_key
from api.identity.dependencies import require_scope
from achievements import create_tracker, get_all_achievements


router = APIRouter(
    prefix="/achievements",
    tags=["achievements"],
    dependencies=[Depends(verify_api_key)],
)


def _get_db(request: Request):
    """Get the database connection from app state."""
    return getattr(request.app.state, "db", None)


def _get_agent_name(request: Request, agent_name: Optional[str] = None) -> str:
    """Get agent name from query param or default."""
    return agent_name or getattr(request.app.state, "default_agent", "default")


@router.get("")
async def get_all(request: Request, agent_name: Optional[str] = None):
    """Get all achievements with their status."""
    db = _get_db(request)
    agent = _get_agent_name(request, agent_name)

    all_achievements = get_all_achievements()
    tracker = create_tracker(user_id=agent, db=db)
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
        "agent_name": agent,
    }


@router.get("/me")
async def get_my_achievements(request: Request, agent_name: Optional[str] = None):
    """Get current user's achievements."""
    db = _get_db(request)
    agent = _get_agent_name(request, agent_name)
    tracker = create_tracker(user_id=agent, db=db)
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
        "agent_name": agent,
    }


@router.get("/{achievement_id}")
async def get_achievement(
    request: Request, achievement_id: str, agent_name: Optional[str] = None
):
    """Get a specific achievement."""
    from achievements.registry import get_achievement

    db = _get_db(request)
    agent = _get_agent_name(request, agent_name)

    achievement = get_achievement(achievement_id)
    if not achievement:
        raise HTTPException(status_code=404, detail="Achievement not found")

    tracker = create_tracker(user_id=agent, db=db)
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
        "agent_name": agent,
    }


@router.post(
    "/{achievement_id}/unlock",
    dependencies=[Depends(require_scope("admin"))],
)
async def unlock_achievement(
    request: Request,
    achievement_id: str,
    context: Optional[dict] = None,
    agent_name: Optional[str] = None,
):
    """Manually unlock an achievement (admin/debug)."""
    from achievements.registry import get_achievement

    db = _get_db(request)
    agent = _get_agent_name(request, agent_name)

    achievement = get_achievement(achievement_id)
    if not achievement:
        raise HTTPException(status_code=404, detail="Achievement not found")

    tracker = create_tracker(user_id=agent, db=db)
    success = await tracker.unlock_specific(achievement_id, context or {})

    if success:
        return {
            "message": f"Unlocked {achievement_id}",
            "xp": tracker.get_xp(),
            "agent_name": agent,
        }
    return {
        "message": f"{achievement_id} already unlocked",
        "xp": tracker.get_xp(),
        "agent_name": agent,
    }
