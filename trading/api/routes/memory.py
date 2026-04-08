"""Memory API — exposes agent memory store and shared market observations."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import verify_api_key
from api.dependencies import get_memory_registry
from api.services.memory_registry import MemoryRegistry

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/engine/v1/memory", tags=["memory"], dependencies=[Depends(verify_api_key)]
)


@router.get("/index")
async def get_memory_index(
    registry: MemoryRegistry = Depends(get_memory_registry)
) -> dict:
    """Return the compressed memory index catalog."""
    shared_client = registry.get_shared()
    if not shared_client:
        raise HTTPException(
            status_code=503, detail="Shared memory system not configured"
        )
    try:
        index_data = await shared_client.get_index()
        return {"index": index_data}
    except Exception as e:
        logger.warning("Failed to fetch memory index: %s", e)
        raise HTTPException(status_code=502, detail="Memory backend error")


@router.get("/search")
async def search_memories(
    agent: str = Query(..., description="Agent name to search"),
    q: str = Query(..., description="Semantic search query"),
    top_k: int = Query(default=5, le=20),
    registry: MemoryRegistry = Depends(get_memory_registry)
) -> dict:
    """Semantic search across agent private + shared market observations."""
    client = registry.get_client(agent)
    if not client:
        raise HTTPException(
            status_code=503, detail="Memory system not available for this agent"
        )
    try:
        results = await client.search_both(q, top_k=top_k)
        return {"agent": agent, "query": q, "results": results}
    except Exception as e:
        logger.warning("Memory search failed for %s: %s", agent, e)
        raise HTTPException(status_code=502, detail="Memory backend error")


@router.get("/market/observations")
async def list_market_observations(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    registry: MemoryRegistry = Depends(get_memory_registry)
) -> dict:
    """List shared market observations, optionally filtered by symbol."""
    shared_client = registry.get_shared()
    if not shared_client:
        raise HTTPException(
            status_code=503, detail="Shared memory system not configured"
        )
    try:
        tag_list = [symbol] if symbol else None
        result = await shared_client._shared.list(tags=tag_list)
        data = result.get("data", result) if isinstance(result, dict) else result
        return {"observations": data[:limit]}
    except Exception as e:
        logger.warning("Failed to list market observations: %s", e)
        raise HTTPException(status_code=502, detail="Memory backend error")


@router.get("/{agent_name}")
async def list_agent_memories(
    agent_name: str,
    tags: str | None = Query(default=None, description="Comma-separated tag filter"),
    limit: int = Query(default=20, le=100),
    registry: MemoryRegistry = Depends(get_memory_registry)
) -> dict:
    """List recent memories for a specific agent."""
    client = registry.get_client(agent_name)
    if not client:
        raise HTTPException(
            status_code=503, detail="Memory system not available for this agent"
        )
    try:
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        result = await client._private.list(tags=tag_list)
        data = result.get("data", result) if isinstance(result, dict) else result
        return {"agent_name": agent_name, "memories": data[:limit]}
    except Exception as e:
        logger.warning("Failed to list memories for %s: %s", agent_name, e)
        raise HTTPException(status_code=502, detail="Memory backend error")
