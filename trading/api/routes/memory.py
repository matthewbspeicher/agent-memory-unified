"""Memory API — exposes agent memory store and shared market observations."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import verify_api_key
from api.dependencies import get_memory_registry
from api.services.memory_registry import MemoryRegistry, SearchTuningConfig

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/engine/v1/memory", tags=["memory"], dependencies=[Depends(verify_api_key)]
)


@router.get("/index")
async def get_memory_index(
    registry: MemoryRegistry = Depends(get_memory_registry),
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
    top_k: int = Query(default=5, le=100),
    # MemClaw filters
    visibility_scope: str | None = Query(
        default=None, description="Filter by scope: scope_agent, scope_team, scope_org"
    ),
    memory_type: str | None = Query(default=None, description="Filter by memory type"),
    status: str | None = Query(default=None, description="Filter by status"),
    min_weight: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum weight filter"
    ),
    freshness_boost: bool = Query(default=False, description="Boost recent memories"),
    registry: MemoryRegistry = Depends(get_memory_registry),
) -> dict:
    """Search memories with MemClaw-compatible filters and tuning.

    Supports visibility scopes, memory types, status filters, and freshness boosting.
    """
    client = registry.get_client(agent)
    if not client:
        raise HTTPException(
            status_code=503, detail="Memory system not available for this agent"
        )
    try:
        # Get tuning config for this agent
        tuning = registry.get_tuning_config(agent)
        results = await client._private.search(
            q,
            agent_id=agent,
            limit=top_k or tuning.top_k,
            visibility_scope=visibility_scope,
            memory_type_filter=memory_type,
            status_filter=status,
            min_weight=max(min_weight, tuning.min_similarity),
            freshness_boost=freshness_boost,
        )
        return {
            "agent": agent,
            "query": q,
            "results": results,
            "tuning": {
                "top_k": tuning.top_k,
                "min_similarity": tuning.min_similarity,
                "similarity_blend": tuning.similarity_blend,
            },
        }
    except Exception as e:
        logger.warning("Memory search failed for %s: %s", agent, e)
        raise HTTPException(status_code=502, detail="Memory backend error")


@router.get("/market/observations")
async def list_market_observations(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    registry: MemoryRegistry = Depends(get_memory_registry),
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
    registry: MemoryRegistry = Depends(get_memory_registry),
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


# --- Search Tuning Endpoints (MemClaw-compatible) ---


class TuningParamsRequest(BaseModel):
    """Request body for setting search tuning parameters."""

    top_k: int = Field(
        default=5, ge=1, le=100, description="Number of results to return"
    )
    min_similarity: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Minimum similarity threshold"
    )
    fts_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Full-text search weight in blended results",
    )
    freshness_floor: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum freshness boost"
    )
    freshness_decay_days: int = Field(
        default=30, ge=1, le=365, description="Days for freshness decay"
    )
    graph_max_hops: int = Field(
        default=1, ge=0, le=5, description="Max graph traversal hops"
    )
    similarity_blend: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Weight for semantic vs FTS blend"
    )


class TuningParamsResponse(BaseModel):
    """Response body for search tuning parameters."""

    agent: str
    top_k: int
    min_similarity: float
    fts_weight: float
    freshness_floor: float
    freshness_decay_days: int
    graph_max_hops: int
    similarity_blend: float


class StatusTransitionRequest(BaseModel):
    """Request body for status transition."""

    status: str = Field(
        ...,
        description="New status (active, pending, confirmed, cancelled, outdated, conflicted, archived, deleted)",
    )


class MemoryResponse(BaseModel):
    """Response body for memory operations."""

    id: str
    agent_id: str | None
    value: str
    memory_type: str | None
    status: str
    weight: float
    visibility_scope: str
    decay_days: int | None
    created_at: str
    updated_at: str


@router.get("/{agent_name}/tune")
async def get_tuning(
    agent_name: str, registry: MemoryRegistry = Depends(get_memory_registry)
) -> TuningParamsResponse:
    """Get current search tuning parameters for an agent."""
    config = registry.get_tuning_config(agent_name)
    return TuningParamsResponse(
        agent=agent_name,
        top_k=config.top_k,
        min_similarity=config.min_similarity,
        fts_weight=config.fts_weight,
        freshness_floor=config.freshness_floor,
        freshness_decay_days=config.freshness_decay_days,
        graph_max_hops=config.graph_max_hops,
        similarity_blend=config.similarity_blend,
    )


@router.post("/{agent_name}/tune")
async def set_tuning(
    agent_name: str,
    params: TuningParamsRequest,
    registry: MemoryRegistry = Depends(get_memory_registry),
) -> TuningParamsResponse:
    """Set search tuning parameters for an agent."""
    config = SearchTuningConfig(
        top_k=params.top_k,
        min_similarity=params.min_similarity,
        fts_weight=params.fts_weight,
        freshness_floor=params.freshness_floor,
        freshness_decay_days=params.freshness_decay_days,
        graph_max_hops=params.graph_max_hops,
        similarity_blend=params.similarity_blend,
    )
    registry.set_tuning_config(agent_name, config)
    logger.info("Updated tuning config for agent %s", agent_name)
    return TuningParamsResponse(agent=agent_name, **params.model_dump())


# --- Status Transition Endpoint (MemClaw lifecycle) ---


@router.post("/{agent_name}/memories/{memory_id}/transition")
async def transition_memory_status(
    agent_name: str,
    memory_id: str,
    body: StatusTransitionRequest,
    registry: MemoryRegistry = Depends(get_memory_registry),
) -> MemoryResponse:
    """Transition a memory to a new status with validation.

    Valid transitions (MemClaw lifecycle):
    - active → pending, confirmed, cancelled, outdated
    - pending → confirmed, cancelled
    - confirmed → outdated, archived
    - cancelled → archived
    - outdated → archived
    - archived → deleted
    """
    client = registry.get_client(agent_name)
    if not client:
        raise HTTPException(
            status_code=503, detail="Memory system not available for this agent"
        )

    try:
        record = await client._private.transition_status(memory_id, body.status)
        if not record:
            raise HTTPException(status_code=404, detail="Memory not found")

        return MemoryResponse(
            id=record.id,
            agent_id=record.agent_id,
            value=record.value,
            memory_type=record.memory_type,
            status=record.status,
            weight=record.weight,
            visibility_scope=record.visibility_scope,
            decay_days=record.computed_decay_days,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.warning(
            "Status transition failed for %s/%s: %s", agent_name, memory_id, e
        )
        raise HTTPException(status_code=502, detail="Memory backend error")
    registry.set_tuning_config(agent_name, config)
    logger.info("Updated tuning config for agent %s", agent_name)
    return TuningParamsResponse(agent=agent_name, **params.model_dump())
