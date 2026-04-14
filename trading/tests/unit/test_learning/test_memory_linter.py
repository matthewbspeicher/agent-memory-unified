import pytest
from unittest.mock import AsyncMock, MagicMock
from learning.memory_linter import MemoryLinter


@pytest.mark.asyncio
async def test_memory_linter_detects_stale_and_orphans():
    mock_client = MagicMock()
    mock_shared = MagicMock()
    mock_shared.search_commons = AsyncMock(return_value=[
        {"id": "1", "expires_at": "2026-01-01T00:00:00Z", "access_count": 5},  # Stale
        {"id": "2", "access_count": 0},  # Orphan
        {"id": "3", "access_count": 10},  # Healthy
    ])
    mock_client._shared = mock_shared

    linter = MemoryLinter(mock_client)
    result = await linter.lint()

    mock_shared.search_commons.assert_awaited_once_with(
        q="", limit=100, tags=["strategy_article"]
    )
    assert result["ok"] is True
    assert result["total_strategies"] == 3
    assert result["stale_articles"] == 1
    assert result["orphan_articles"] == 1


@pytest.mark.asyncio
async def test_memory_linter_returns_error_on_exception():
    mock_client = MagicMock()
    mock_shared = MagicMock()
    mock_shared.search_commons = AsyncMock(side_effect=RuntimeError("network down"))
    mock_client._shared = mock_shared

    linter = MemoryLinter(mock_client)
    result = await linter.lint()

    assert result["ok"] is False
    assert "network down" in result["error"]
