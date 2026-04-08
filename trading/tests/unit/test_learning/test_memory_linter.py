import pytest
from unittest.mock import AsyncMock, MagicMock
from learning.memory_linter import MemoryLinter

@pytest.mark.asyncio
async def test_memory_linter_detects_stale_and_orphans():
    # Mock Memory Client
    mock_client = MagicMock()
    mock_shared = MagicMock()
    mock_resp = MagicMock()
    mock_resp.is_error = False
    mock_resp.json.return_value = {
        "data": [
            {"id": "1", "expires_at": "2026-01-01T00:00:00Z", "access_count": 5}, # Stale
            {"id": "2", "access_count": 0}, # Orphan
            {"id": "3", "access_count": 10} # Healthy
        ]
    }
    mock_shared.client.get = AsyncMock(return_value=mock_resp)
    mock_client._shared = mock_shared
    
    linter = MemoryLinter(mock_client)
    result = await linter.lint()
    
    assert result["ok"] is True
    assert result["total_strategies"] == 3
    assert result["stale_articles"] == 1
    assert result["orphan_articles"] == 1
