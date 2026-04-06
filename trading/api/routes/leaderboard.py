"""GET /leaderboard — agent rivalry leaderboard."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.auth import verify_api_key

router = APIRouter()


@router.get("/leaderboard")
async def leaderboard(
    request: Request,
    _: str = Depends(verify_api_key),
):
    engine = getattr(request.app.state, "leaderboard_engine", None)
    if engine is None:
        return JSONResponse(
            status_code=501, content={"detail": "Leaderboard not configured"}
        )

    sync = engine._remembr_sync
    runner = engine._runner
    agent_names = [a.name for a in runner.list_agents()]

    # Check for new data
    if not await engine.is_stale():
        cached = await engine.get_cached_leaderboard()
        if cached:
            return {
                "rankings": [asdict(r) for r in cached],
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "source": "cached",
            }

    # Try full orchestration
    profiles = None
    agent_map = {}
    if sync:
        agent_map = await sync.ensure_agents_registered(agent_names)
        profiles = await sync.fetch_all_profiles(agent_map)

    if profiles is None and sync:
        # Remembr sync failed — fall through to compute rankings without profiles
        # rather than returning an empty leaderboard
        profiles = None

    rankings = await engine.compute_rankings(profiles)
    if not rankings:
        return {
            "rankings": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "live",
        }

    matches = engine.run_matches(rankings)
    rankings = engine.tally_results(matches, rankings)
    current_elo = {r.agent_name: r.elo for r in rankings}
    new_elo = engine.update_elo(matches, current_elo)
    for r in rankings:
        r.elo = new_elo.get(r.agent_name, r.elo)

    if sync and agent_map:
        await sync.push_matches(matches, agent_map)
        for r in rankings:
            await sync.push_profile(r.agent_name, r, agent_map)

    snapshot_ts = await engine.get_latest_snapshot_ts() or ""
    await engine.save_cache(rankings, snapshot_ts, source="live")

    return {
        "rankings": [asdict(r) for r in rankings],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "live",
    }
