"""Tests for MemoryIndexService — covers the FIXME-removal switch from
raw HTTP bypass to the SDK's search_commons method."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from learning.strategy_index import MemoryIndexService


def _client_with_articles(articles: list[dict]) -> MagicMock:
    mock_client = MagicMock()
    mock_shared = MagicMock()
    mock_shared.search_commons = AsyncMock(return_value=articles)
    mock_client._shared = mock_shared
    return mock_client


@pytest.mark.asyncio
async def test_get_compressed_index_uses_search_commons_sdk():
    client = _client_with_articles(
        [
            {"id": "a1", "tags": ["strategy_article"], "value": "RSI < 30 buy signal " * 20},
            {"id": "a2", "tags": ["strategy_article"], "value": "MACD crossover"},
        ]
    )
    svc = MemoryIndexService(client)

    index = await svc.get_compressed_index()

    client._shared.search_commons.assert_awaited_once_with(
        q="", limit=100, tags=["strategy_article"]
    )
    assert len(index) == 2
    assert index[0]["id"] == "a1"
    assert index[0]["tags"] == ["strategy_article"]
    assert index[0]["summary"].endswith("...")
    # Summary capped near 150 chars before the ellipsis
    assert len(index[0]["summary"]) <= 153


@pytest.mark.asyncio
async def test_get_compressed_index_falls_back_to_key_for_missing_id():
    client = _client_with_articles([{"key": "k1", "value": "x"}])
    svc = MemoryIndexService(client)

    index = await svc.get_compressed_index()

    assert index[0]["id"] == "k1"


@pytest.mark.asyncio
async def test_get_compressed_index_returns_empty_on_error():
    mock_client = MagicMock()
    mock_shared = MagicMock()
    mock_shared.search_commons = AsyncMock(side_effect=RuntimeError("boom"))
    mock_client._shared = mock_shared
    svc = MemoryIndexService(mock_client)

    assert await svc.get_compressed_index() == []
