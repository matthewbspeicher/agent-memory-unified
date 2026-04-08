import pytest
from unittest.mock import AsyncMock, MagicMock
from learning.trade_compiler import DailyTradeCompiler

@pytest.mark.asyncio
async def test_compile_daily_summary():
    mock_memory = MagicMock()
    mock_memory.search_both = AsyncMock(return_value=[
        {"value": "Trade 1", "tags": ["trade"]},
        {"value": "Observation 1", "tags": ["market_observation"]}
    ])
    mock_memory.store_private = AsyncMock()
    
    mock_llm = MagicMock()
    mock_result = MagicMock()
    mock_result.text = "## Trades Executed\nMock Summary"
    mock_llm.complete = AsyncMock(return_value=mock_result)
    
    compiler = DailyTradeCompiler(mock_memory, mock_llm)
    summary = await compiler.compile_daily_summary()
    
    assert "Mock Summary" in summary
    mock_memory.search_both.assert_called_once()
    mock_llm.complete.assert_called_once()
    mock_memory.store_private.assert_called_once()
