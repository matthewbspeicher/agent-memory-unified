"""Tests for TradingMemoryClient.search_by_keys — covers the FIXME removal
that swapped raw HTTP for the SDK's get_commons(key) method."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from learning.memory_client import TradingMemoryClient


def _client(get_commons_side_effect=None, get_commons_return=None) -> TradingMemoryClient:
    private = MagicMock()
    shared = MagicMock()
    if get_commons_side_effect is not None:
        shared.get_commons = AsyncMock(side_effect=get_commons_side_effect)
    else:
        shared.get_commons = AsyncMock(return_value=get_commons_return)
    return TradingMemoryClient(private_client=private, shared_client=shared)


@pytest.mark.asyncio
async def test_search_by_keys_calls_get_commons_per_key():
    payloads = {"k1": {"id": "k1", "value": "v1"}, "k2": {"id": "k2", "value": "v2"}}

    client = _client()
    client._shared.get_commons = AsyncMock(side_effect=lambda k: payloads[k])

    results = await client.search_by_keys(["k1", "k2"])

    assert results == [payloads["k1"], payloads["k2"]]
    assert client._shared.get_commons.await_count == 2


@pytest.mark.asyncio
async def test_search_by_keys_skips_failures_and_keeps_successes():
    def fake_get_commons(key):
        if key == "bad":
            raise RuntimeError("404 not found")
        return {"id": key, "value": f"v-{key}"}

    client = _client()
    client._shared.get_commons = AsyncMock(side_effect=fake_get_commons)

    results = await client.search_by_keys(["good1", "bad", "good2"])

    assert len(results) == 2
    assert results[0]["id"] == "good1"
    assert results[1]["id"] == "good2"


@pytest.mark.asyncio
async def test_search_by_keys_empty_input_returns_empty():
    client = _client(get_commons_return={})

    results = await client.search_by_keys([])

    assert results == []
    client._shared.get_commons.assert_not_awaited()
