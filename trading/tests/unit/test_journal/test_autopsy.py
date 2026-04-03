"""Tests for AutopsyGenerator."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal


def _make_position(position_id=42, agent_name="rsi_scanner", symbol="AAPL",
                   side="buy", entry_price="182.50", exit_price="188.30",
                   entry_quantity=10, entry_fees="2.00", exit_fees="2.00",
                   entry_time="2026-03-24T14:30:00", exit_time="2026-03-26T09:15:00",
                   opportunity_id="opp-123", max_adverse_excursion="-12.00",
                   exit_reason="take_profit"):
    return {
        "id": position_id, "agent_name": agent_name, "symbol": symbol,
        "side": side, "entry_price": entry_price, "exit_price": exit_price,
        "entry_quantity": entry_quantity, "entry_fees": entry_fees,
        "exit_fees": exit_fees, "entry_time": entry_time, "exit_time": exit_time,
        "opportunity_id": opportunity_id, "max_adverse_excursion": max_adverse_excursion,
        "exit_reason": exit_reason, "status": "closed",
    }


@pytest.fixture
def mock_db():
    db = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=cursor)
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_opp_store():
    store = MagicMock()
    store.get = AsyncMock(return_value={
        "id": "opp-123", "agent_name": "rsi_scanner", "symbol": "AAPL",
        "signal": "BUY", "confidence": 0.82,
        "reasoning": "RSI dropped below 30, oversold signal",
        "data": json.dumps({"rsi": 28.5}),
    })
    store.get_snapshot = AsyncMock(return_value={
        "quote": {"bid": 182.40, "ask": 182.60, "last": 182.50, "volume": 15000},
    })
    return store


@pytest.mark.asyncio
async def test_anthropic_provider_generates_and_caches(mock_db, mock_opp_store):
    from journal.autopsy import AutopsyGenerator

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=MagicMock(text="RSI signal fired correctly. Entry was well-timed."))

    gen = AutopsyGenerator(
        db=mock_db, opp_store=mock_opp_store,
        llm=mock_llm,
    )

    result = await gen.generate(_make_position())
    assert "RSI signal fired correctly" in result
    mock_db.execute.assert_awaited()


@pytest.mark.asyncio
async def test_openai_compatible_provider(mock_db, mock_opp_store):
    from journal.autopsy import AutopsyGenerator

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=MagicMock(text="Trade analysis complete."))

    gen = AutopsyGenerator(
        db=mock_db, opp_store=mock_opp_store,
        llm=mock_llm,
    )

    result = await gen.generate(_make_position())
    assert "Trade analysis complete" in result


@pytest.mark.asyncio
async def test_cache_hit_skips_llm(mock_db, mock_opp_store):
    from journal.autopsy import AutopsyGenerator

    # Simulate cache hit
    cached_cursor = AsyncMock()
    cached_cursor.fetchone = AsyncMock(return_value=("Cached autopsy.",))
    mock_db.execute = AsyncMock(return_value=cached_cursor)

    mock_llm = AsyncMock()
    gen = AutopsyGenerator(
        db=mock_db, opp_store=mock_opp_store,
        llm=mock_llm,
    )

    result = await gen.get_or_generate(_make_position())
    assert result == "Cached autopsy."


@pytest.mark.asyncio
async def test_no_api_key_returns_fallback(mock_db, mock_opp_store):
    from journal.autopsy import AutopsyGenerator

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=Exception("No API key configured"))
    gen = AutopsyGenerator(
        db=mock_db, opp_store=mock_opp_store,
        llm=mock_llm,
    )

    result = await gen.get_or_generate(_make_position())
    assert "AAPL" in result
    assert "182.50" in result
    assert "188.30" in result


@pytest.mark.asyncio
async def test_context_includes_all_four_sources(mock_db, mock_opp_store):
    """Verify the prompt includes trade, opportunity, snapshot, and lessons."""
    from journal.autopsy import AutopsyGenerator

    # Mock lessons query
    lessons_cursor = AsyncMock()
    lessons_cursor.fetchall = AsyncMock(return_value=[
        {"lesson": "Momentum reversals are risky after 3pm", "category": "timing"},
    ])

    call_count = 0
    original_cursor = AsyncMock()
    original_cursor.fetchone = AsyncMock(return_value=None)

    async def side_effect_execute(query, params=None):
        nonlocal call_count
        call_count += 1
        if "llm_lessons" in str(query):
            return lessons_cursor
        if "trade_autopsies" in str(query) and "SELECT" in str(query):
            return original_cursor
        return original_cursor

    mock_db.execute = AsyncMock(side_effect=side_effect_execute)

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=MagicMock(text="Analysis."))
    gen = AutopsyGenerator(
        db=mock_db, opp_store=mock_opp_store,
        llm=mock_llm,
    )

    await gen.generate(_make_position())

    # Check the prompt sent to LLM contains all 4 sources
    call_args = mock_llm.complete.call_args
    prompt = call_args.args[0]
    assert "AAPL" in prompt            # trade
    assert "RSI dropped" in prompt     # opportunity reasoning
    assert "182.40" in prompt          # market snapshot bid
    assert "Momentum" in prompt        # agent lesson
