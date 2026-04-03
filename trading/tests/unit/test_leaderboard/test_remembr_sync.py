"""Tests for RemembrArenaSync."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from leaderboard.engine import AgentRanking, MatchResult


@pytest.fixture
def mock_db():
    db = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    cursor.fetchall = AsyncMock(return_value=[])
    db.execute = AsyncMock(return_value=cursor)
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_ensure_agents_registered_creates_mapping(mock_db):
    from leaderboard.remembr_sync import RemembrArenaSync
    sync = RemembrArenaSync(token="test_token", db=mock_db)

    with patch("leaderboard.remembr_sync.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"data": [{"id": "rem-123", "name": "rsi_scanner"}]},
        ))
        mock_client_cls.return_value = mock_client

        result = await sync.ensure_agents_registered(["rsi_scanner"])
        assert "rsi_scanner" in result


@pytest.mark.asyncio
async def test_fetch_all_profiles_returns_none_on_timeout(mock_db):
    from leaderboard.remembr_sync import RemembrArenaSync
    sync = RemembrArenaSync(token="test_token", db=mock_db, timeout=1)

    with patch("leaderboard.remembr_sync.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        import httpx
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_cls.return_value = mock_client

        result = await sync.fetch_all_profiles({"rsi_scanner": "rem-123"})
        assert result is None


@pytest.mark.asyncio
async def test_push_profile_fail_open(mock_db):
    """Exception in push_profile → warning logged, no crash."""
    from leaderboard.remembr_sync import RemembrArenaSync
    sync = RemembrArenaSync(token="test_token", db=mock_db)

    with patch("leaderboard.remembr_sync.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.put = AsyncMock(side_effect=Exception("network error"))
        mock_client_cls.return_value = mock_client

        ranking = AgentRanking(
            agent_name="rsi_scanner", sharpe_ratio=1.5,
            total_pnl=100.0, win_rate=0.7, elo=1100,
            win_count=5, loss_count=2, streak=3,
        )
        # Should not raise
        await sync.push_profile("rsi_scanner", ranking, {"rsi_scanner": "rem-123"})
