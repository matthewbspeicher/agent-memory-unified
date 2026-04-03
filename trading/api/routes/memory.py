"""Memory API — exposes agent memory store and shared market observations."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"], dependencies=[Depends(verify_api_key)])

# Injected at startup by app.py
_memory_client_registry: dict[str, Any] = {}   # agent_name -> TradingMemoryClient
_shared_memory_client: Any = None              # TradingMemoryClient for market:observations


def register_memory_client(agent_name: str, client: Any) -> None:
    _memory_client_registry[agent_name] = client


def register_shared_client(client: Any) -> None:
    global _shared_memory_client
    _shared_memory_client = client


@router.get("/search")
async def search_memories(
    agent: str = Query(..., description="Agent name to search"),
    q: str = Query(..., description="Semantic search query"),
    top_k: int = Query(default=5, le=20),
) -> dict:
    """Semantic search across agent private + shared market observations."""
    client = _memory_client_registry.get(agent)
    if not client:
        raise HTTPException(status_code=503, detail="Memory system not available for this agent")
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
) -> dict:
    """List shared market observations, optionally filtered by symbol."""
    if not _shared_memory_client:
        raise HTTPException(status_code=503, detail="Shared memory system not configured")
    try:
        tag_list = [symbol] if symbol else None
        result = await _shared_memory_client._shared.list(tags=tag_list)
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
) -> dict:
    """List recent memories for a specific agent."""
    client = _memory_client_registry.get(agent_name)
    if not client:
        raise HTTPException(status_code=503, detail="Memory system not available for this agent")
    try:
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        result = await client._private.list(tags=tag_list)
        data = result.get("data", result) if isinstance(result, dict) else result
        return {"agent_name": agent_name, "memories": data[:limit]}
    except Exception as e:
        logger.warning("Failed to list memories for %s: %s", agent_name, e)
        raise HTTPException(status_code=502, detail="Memory backend error")
