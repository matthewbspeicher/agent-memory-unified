"""Public router — curated read-only endpoints for external agents.

Every endpoint here is anonymous-allowed and rate-limited at the anonymous
tier (10 req/min) via the defensive_perimeter middleware. No mutation
methods may be called from this file. Enforced by test_public_surface_scoping.

See conductor/tracks/public_surface/spec.md for design.
"""

from __future__ import annotations

import time
from pathlib import Path
from fastapi import APIRouter, Request

router = APIRouter(prefix="/engine/v1/public", tags=["public"])

_STARTUP_TIME = time.time()


def _base_response() -> dict:
    """Common fields every public response includes."""
    return {
        "schema_version": "1.0",
        "name": "agent-memory-unified",
        "served_by": "agent-memory-unified",
        "docs": "/FOR_AGENTS.md",
    }


@router.get("/status")
async def public_status():
    return {
        **_base_response(),
        "version": "0.1.0",
        "uptime_seconds": int(time.time() - _STARTUP_TIME),
    }


@router.get("/agents")
async def public_agents(request: Request):
    import yaml

    agents_yaml_path = Path(__file__).parent.parent.parent / "agents.yaml"
    if agents_yaml_path.exists():
        agents_data = yaml.safe_load(agents_yaml_path.read_text())
        agents = [
            {
                "name": a["name"],
                "strategy": a.get("strategy", "unknown"),
                "description": a.get("description", ""),
                "action_level": a.get("action_level", "notify"),
            }
            for a in agents_data.get("agents", [])
        ]
    else:
        agents = []
    return {**_base_response(), "agents": agents}


@router.get("/arena/state")
async def public_arena_state(request: Request):
    arena = getattr(request.app.state, "arena_manager", None)
    if not arena:
        return {
            **_base_response(),
            "note": "Arena not initialized",
            "top_leaderboard": [],
        }
    state = {
        "current_match": await arena.get_current_match_public()
        if hasattr(arena, "get_current_match_public")
        else None,
        "season": await arena.get_current_season_public()
        if hasattr(arena, "get_current_season_public")
        else None,
        "top_leaderboard": await arena.get_top_leaderboard(limit=5)
        if hasattr(arena, "get_top_leaderboard")
        else [],
    }
    return {**_base_response(), **state}


@router.get("/leaderboard")
async def public_leaderboard(request: Request):
    arena = getattr(request.app.state, "arena_manager", None)
    if not arena:
        return {**_base_response(), "leaderboard": [], "as_of": None}
    leaderboard = (
        await arena.get_leaderboard(limit=50)
        if hasattr(arena, "get_leaderboard")
        else []
    )
    return {
        **_base_response(),
        "leaderboard": leaderboard,
        "as_of": leaderboard[0]["as_of"] if leaderboard else None,
    }


@router.get("/kg/entity/{name}")
async def public_kg_entity(name: str, request: Request, direction: str = "both"):
    kg = getattr(request.app.state, "knowledge_graph", None)
    if not kg:
        return {
            **_base_response(),
            "entity": name,
            "facts": [],
            "count": 0,
            "note": "KG not initialized",
        }
    facts = (
        await kg.query_entity_public(name, direction=direction)
        if hasattr(kg, "query_entity_public")
        else []
    )
    return {**_base_response(), "entity": name, "facts": facts, "count": len(facts)}


@router.get("/kg/timeline")
async def public_kg_timeline(
    request: Request, entity: str | None = None, limit: int = 50
):
    kg = getattr(request.app.state, "knowledge_graph", None)
    if not kg:
        return {**_base_response(), "entity": entity, "timeline": [], "count": 0}
    timeline = (
        await kg.timeline_public(entity_name=entity, limit=min(limit, 50))
        if hasattr(kg, "timeline_public")
        else []
    )
    return {
        **_base_response(),
        "entity": entity,
        "timeline": timeline,
        "count": len(timeline),
    }


@router.get("/milestones")
async def public_milestones():
    import re

    feed_dir = Path(__file__).parent.parent.parent.parent / "project-feed"
    if not feed_dir.exists():
        return {**_base_response(), "milestones": []}
    posted = []
    for md in sorted(feed_dir.glob("*.md"), reverse=True):
        if md.name == "README.md":
            continue
        content = md.read_text()
        fm_match = re.search(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if not fm_match:
            continue
        fm = fm_match.group(1)
        if "status: posted" not in fm:
            continue
        title_match = re.search(r"^title:\s*[\"']?(.+?)[\"']?\s*$", fm, re.MULTILINE)
        summary_match = re.search(
            r"^summary:\s*[\"']?(.+?)[\"']?\s*$", fm, re.MULTILINE
        )
        posted.append(
            {
                "slug": md.stem,
                "title": title_match.group(1) if title_match else md.stem,
                "summary": summary_match.group(1) if summary_match else "",
            }
        )
        if len(posted) >= 20:
            break
    return {**_base_response(), "milestones": posted}


@router.get("/for-agents", include_in_schema=True)
async def public_for_agents():
    from fastapi.responses import Response

    md_path = Path(__file__).parent.parent.parent / "public_content" / "FOR_AGENTS.md"
    if not md_path.exists():
        return Response(
            content="# FOR_AGENTS.md not found\n",
            media_type="text/markdown",
            status_code=404,
        )
    return Response(content=md_path.read_text(), media_type="text/markdown")


@router.get("/agents.json", include_in_schema=True)
async def public_agents_json():
    import json
    from fastapi.responses import JSONResponse

    json_path = Path(__file__).parent.parent.parent / "public_content" / "agents.json"
    if not json_path.exists():
        return JSONResponse(content={"error": "agents.json not found"}, status_code=404)
    return JSONResponse(content=json.loads(json_path.read_text()))


@router.get("/status")
async def public_status():
    return {
        **_base_response(),
        "version": "0.1.0",
        "uptime_seconds": int(time.time() - _STARTUP_TIME),
    }
