import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest
from observability.heartbeat_watchdog import check_heartbeats


@pytest.mark.asyncio
async def test_stale_agent_fires_critical_alert():
    emitter = MagicMock()
    emitter.emit = AsyncMock()

    now = datetime.now(timezone.utc)
    stale_time = (now - timedelta(seconds=300)).isoformat()

    mock_sb = MagicMock()
    mock_table = MagicMock()
    mock_table.select = MagicMock(return_value=mock_table)
    mock_table.execute = AsyncMock(return_value=MagicMock(data=[
        {"agent_name": "rsi_agent", "last_seen": stale_time, "status": "running", "cycle_count": 5},
    ]))
    mock_sb.table = MagicMock(return_value=mock_table)

    # 120s threshold — agent last seen 300s ago -> stale
    await check_heartbeats(supabase_client=mock_sb, emitter=emitter, threshold_seconds=120)

    emitter.emit.assert_awaited_once()
    call_kwargs = emitter.emit.call_args[1]
    assert call_kwargs["level"] == "critical"
    assert "rsi_agent" in call_kwargs["message"]


@pytest.mark.asyncio
async def test_fresh_agent_does_not_alert():
    emitter = MagicMock()
    emitter.emit = AsyncMock()

    now = datetime.now(timezone.utc)
    fresh_time = (now - timedelta(seconds=30)).isoformat()

    mock_sb = MagicMock()
    mock_table = MagicMock()
    mock_table.select = MagicMock(return_value=mock_table)
    mock_table.execute = AsyncMock(return_value=MagicMock(data=[
        {"agent_name": "rsi_agent", "last_seen": fresh_time, "status": "running", "cycle_count": 10},
    ]))
    mock_sb.table = MagicMock(return_value=mock_table)

    await check_heartbeats(supabase_client=mock_sb, emitter=emitter, threshold_seconds=120)

    emitter.emit.assert_not_awaited()
