"""Unit tests for MemoryConsolidator.

Covers the proper LLMClient wiring (no more hasattr ducktyping) and the
graceful-skip behavior when the LLM returns empty / raises.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from integrations.memory.consolidator import MemoryConsolidator


def _payload(n: int = 2) -> dict:
    return {
        "agent_id": 7,
        "memory_ids": list(range(n)),
        "memories": [
            {
                "id": i,
                "type": "fact",
                "summary": f"summary {i}",
                "value": f"value {i}",
                "created_at": "2026-04-14T00:00:00Z",
            }
            for i in range(n)
        ],
    }


def _make_llm(text: str = "consolidated text", raises: Exception | None = None) -> MagicMock:
    llm = MagicMock()
    if raises is not None:
        llm.complete = AsyncMock(side_effect=raises)
    else:
        result = MagicMock()
        result.text = text
        llm.complete = AsyncMock(return_value=result)
    return llm


def _make_redis() -> MagicMock:
    redis = MagicMock()
    redis.xadd = AsyncMock()
    return redis


@pytest.mark.asyncio
async def test_consolidate_calls_llm_complete_and_publishes():
    llm = _make_llm(text="new merged insight")
    redis = _make_redis()
    consolidator = MemoryConsolidator(llm_client=llm, redis_client=redis)

    await consolidator.consolidate(_payload(3))

    llm.complete.assert_awaited_once()
    # The prompt argument is positional
    prompt = llm.complete.call_args.args[0]
    assert "trading agent" in prompt
    assert "value 0" in prompt

    redis.xadd.assert_awaited_once()
    stream, fields = redis.xadd.call_args.args
    assert stream == "events"
    event = json.loads(fields["data"])
    assert event["type"] == "memory.consolidation.completed"
    assert event["payload"]["agent_id"] == 7
    assert event["payload"]["consolidated_memory"]["value"] == "new merged insight"


@pytest.mark.asyncio
async def test_consolidate_skips_when_no_memories():
    llm = _make_llm()
    redis = _make_redis()
    consolidator = MemoryConsolidator(llm_client=llm, redis_client=redis)

    await consolidator.consolidate({"agent_id": 1, "memories": []})

    llm.complete.assert_not_awaited()
    redis.xadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_consolidate_skips_when_llm_returns_empty():
    """No more mock-string fallback — empty LLM output means skip."""
    llm = _make_llm(text="")
    redis = _make_redis()
    consolidator = MemoryConsolidator(llm_client=llm, redis_client=redis)

    await consolidator.consolidate(_payload())

    llm.complete.assert_awaited_once()
    redis.xadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_consolidate_skips_on_llm_exception():
    llm = _make_llm(raises=RuntimeError("provider down"))
    redis = _make_redis()
    consolidator = MemoryConsolidator(llm_client=llm, redis_client=redis)

    await consolidator.consolidate(_payload())

    llm.complete.assert_awaited_once()
    redis.xadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_consolidate_strips_whitespace_only_output():
    llm = _make_llm(text="   \n  \t  ")
    redis = _make_redis()
    consolidator = MemoryConsolidator(llm_client=llm, redis_client=redis)

    await consolidator.consolidate(_payload())

    redis.xadd.assert_not_awaited()
