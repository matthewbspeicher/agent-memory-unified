import pytest
from unittest.mock import MagicMock, AsyncMock
from remembr.trading import TradingJournal
from remembr.turbo import TurboContextLoader

@pytest.mark.asyncio
async def test_trading_journal_execute():
    # Setup
    mock_client = MagicMock()
    mock_client.store = AsyncMock(return_value={"key": "mem-123"})
    
    # Mock the internal httpx client used for /trading/trades
    mock_resp = MagicMock()
    mock_resp.is_error = False
    mock_resp.json.return_value = {"trade_id": "trade-456", "status": "executed"}
    mock_client.client.post = AsyncMock(return_value=mock_resp)
    
    journal = TradingJournal(client=mock_client)
    
    # Test
    res = await journal.execute_trade(
        ticker="BTCUSD",
        direction="buy",
        price=65000.0,
        quantity=1.0,
        reasoning="Bittensor consensus + Twitter bullish"
    )
    
    # Verify 2-phase commit
    assert mock_client.store.called
    assert mock_client.client.post.called
    assert res["trade_id"] == "trade-456"
    assert res["memory_id"] == "mem-123"

def test_turbo_context_loader_fallback():
    loader = TurboContextLoader()
    memories = [{"value": "test memory"}]
    
    # Without turboquant installed, should return raw memories
    res = loader.prepare_cache(memories, model=None)
    assert res == memories
    
    stats = loader.benchmark(memories)
    assert stats["speedup"] >= 1.0
