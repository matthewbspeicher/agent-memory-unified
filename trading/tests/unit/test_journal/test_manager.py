import pytest
from unittest.mock import AsyncMock, MagicMock

from journal.manager import JournalManager
from journal.models import TradeLifecycle, TradeDecision


@pytest.fixture
def remembr_client():
    client = AsyncMock()
    client.store = AsyncMock(return_value={"id": "mem-123"})
    client.search = AsyncMock(return_value=[])
    client.get = AsyncMock(return_value={"value": "old", "metadata": {}, "tags": []})
    return client


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def indexer():
    idx = MagicMock()
    idx.is_ready = True
    idx.search = MagicMock(return_value=[])
    idx.get_by_symbol = MagicMock(return_value=[])
    return idx


@pytest.mark.asyncio
async def test_log_trade_publishes_event(remembr_client, event_bus):
    mgr = JournalManager(client=remembr_client, event_bus=event_bus)
    lifecycle = TradeLifecycle(
        trade_id="t-1",
        decision=TradeDecision(
            agent_name="agent1",
            symbol="AAPL",
            direction="BUY",
            confidence=0.9,
            reasoning="test",
        ),
    )
    result = await mgr.log_trade(lifecycle)

    assert result == "mem-123"
    event_bus.publish.assert_called_once()
    call_args = event_bus.publish.call_args
    assert call_args[0][0] == "journal.entry_added"
    assert call_args[0][1]["memory_id"] == "mem-123"
    assert call_args[0][1]["trade_id"] == "t-1"


@pytest.mark.asyncio
async def test_log_trade_no_event_without_bus(remembr_client):
    mgr = JournalManager(client=remembr_client)
    lifecycle = TradeLifecycle(
        trade_id="t-1",
        decision=TradeDecision(
            agent_name="agent1",
            symbol="AAPL",
            direction="BUY",
            confidence=0.9,
            reasoning="test",
        ),
    )
    result = await mgr.log_trade(lifecycle)
    assert result == "mem-123"


@pytest.mark.asyncio
async def test_query_similar_uses_indexer(remembr_client, event_bus, indexer):
    from journal.indexer import SearchResult

    indexer.search.return_value = [
        SearchResult(
            memory_id="m-1",
            score=0.95,
            content="Trade AAPL",
            metadata={"status": "open"},
        ),
    ]
    mgr = JournalManager(client=remembr_client, event_bus=event_bus, indexer=indexer)

    results = await mgr.query_similar_trades("AAPL BUY", limit=5)

    assert len(results) == 1
    assert results[0]["id"] == "m-1"
    assert results[0]["score"] == 0.95
    remembr_client.search.assert_not_called()


@pytest.mark.asyncio
async def test_query_similar_falls_back_when_not_ready(
    remembr_client, event_bus, indexer
):
    indexer.is_ready = False
    remembr_client.search = AsyncMock(return_value=[{"id": "r-1", "metadata": {}}])
    mgr = JournalManager(client=remembr_client, event_bus=event_bus, indexer=indexer)

    await mgr.query_similar_trades("AAPL", limit=5)
    remembr_client.search.assert_called_once()


@pytest.mark.asyncio
async def test_get_recent_uses_indexer_directly(remembr_client, event_bus, indexer):
    from journal.indexer import SearchResult

    indexer.get_by_symbol.return_value = [
        SearchResult(
            memory_id="m-1",
            score=None,
            content="Trade AAPL",
            metadata={"decision": {"timestamp": "2026-04-01"}},
        ),
    ]
    mgr = JournalManager(client=remembr_client, event_bus=event_bus, indexer=indexer)

    results = await mgr.get_recent_trades("AAPL", limit=10)

    assert len(results) == 1
    indexer.get_by_symbol.assert_called_once_with("AAPL", 10)
    remembr_client.search.assert_not_called()


@pytest.mark.asyncio
async def test_get_recent_falls_back_when_no_indexer(remembr_client):
    remembr_client.search = AsyncMock(
        return_value=[
            {
                "id": "r-1",
                "metadata": {"decision": {"timestamp": "2026-04-01T00:00:00+00:00"}},
            }
        ]
    )
    mgr = JournalManager(client=remembr_client)

    await mgr.get_recent_trades("AAPL", limit=10)
    remembr_client.search.assert_called_once()
