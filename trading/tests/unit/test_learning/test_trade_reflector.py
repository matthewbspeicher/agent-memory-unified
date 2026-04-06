import json
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from learning.trade_memory import TradeMemory, ClosedTrade
from learning.memory_client import TradingMemoryClient
from learning.trade_reflector import TradeReflector


def test_trade_memory_outcome_win():
    m = TradeMemory(
        symbol="AAPL",
        direction="long",
        entry_price=Decimal("150.00"),
        exit_price=Decimal("156.00"),
        pnl=Decimal("6.00"),
        slippage_bps=3,
        signal_strength=0.8,
        outcome="win",
        hold_duration_mins=45,
        timestamp=datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
    )
    assert m.outcome == "win"
    assert m.pnl > 0


def test_closed_trade_fields():
    ct = ClosedTrade(
        agent_name="momentum_agent",
        opportunity_id="opp-001",
        trade_memory=TradeMemory(
            symbol="NVDA",
            direction="long",
            entry_price=Decimal("800.00"),
            exit_price=Decimal("780.00"),
            pnl=Decimal("-20.00"),
            slippage_bps=5,
            signal_strength=0.6,
            outcome="loss",
            hold_duration_mins=120,
            timestamp=datetime(2026, 3, 27, 11, 0, tzinfo=timezone.utc),
        ),
        expected_pnl=Decimal("-5.00"),
        stop_loss=Decimal("-10.00"),
    )
    assert ct.trade_memory.outcome == "loss"
    assert ct.expected_pnl == Decimal("-5.00")


@pytest.fixture
def mock_private_client():
    c = AsyncMock()
    c.search = AsyncMock(
        return_value=[{"value": "AAPL fades on heavy volume", "tags": ["AAPL", "win"]}]
    )
    c.store = AsyncMock(return_value={"id": "mem-001"})
    return c


@pytest.fixture
def mock_shared_client():
    c = AsyncMock()
    c.search_commons = AsyncMock(
        return_value=[{"value": "NVDA tends to fade first 30min", "tags": ["NVDA"]}]
    )
    c.store = AsyncMock(return_value={"id": "mem-002"})
    return c


@pytest.mark.asyncio
async def test_memory_client_store_private(mock_private_client, mock_shared_client):
    client = TradingMemoryClient(
        private_client=mock_private_client,
        shared_client=mock_shared_client,
        ttl_days=90,
    )
    await client.store_private("lesson about AAPL", tags=["AAPL", "win"])
    mock_private_client.store.assert_awaited_once()
    call_kwargs = mock_private_client.store.call_args.kwargs
    assert call_kwargs["ttl"] == "90d"
    assert "AAPL" in call_kwargs["tags"]


@pytest.mark.asyncio
async def test_memory_client_store_shared(mock_private_client, mock_shared_client):
    client = TradingMemoryClient(
        private_client=mock_private_client,
        shared_client=mock_shared_client,
        ttl_days=90,
    )
    await client.store_shared("NVDA fades on volume", tags=["NVDA"])
    mock_shared_client.store.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_client_search_both(mock_private_client, mock_shared_client):
    client = TradingMemoryClient(
        private_client=mock_private_client,
        shared_client=mock_shared_client,
        ttl_days=90,
    )
    results = await client.search_both("AAPL volume fade", top_k=5)
    assert len(results) == 2
    mock_private_client.search.assert_awaited_once()
    mock_shared_client.search_commons.assert_awaited_once()


def make_closed_trade(
    pnl: Decimal, expected_pnl: Decimal, stop_loss: Decimal, outcome: str = "win"
) -> ClosedTrade:
    return ClosedTrade(
        agent_name="test_agent",
        opportunity_id="opp-001",
        trade_memory=TradeMemory(
            symbol="AAPL",
            direction="long",
            entry_price=Decimal("150.00"),
            exit_price=Decimal("160.00"),
            pnl=pnl,
            slippage_bps=3,
            signal_strength=0.75,
            outcome=outcome,
            hold_duration_mins=60,
            timestamp=datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
        ),
        expected_pnl=expected_pnl,
        stop_loss=stop_loss,
    )


@pytest.fixture
def memory_client():
    mc = AsyncMock(spec=TradingMemoryClient)
    mc.store_private = AsyncMock(return_value={"id": "mem-1"})
    mc.store_shared = AsyncMock(return_value={"id": "mem-2"})
    mc.search_both = AsyncMock(return_value=[])
    return mc


@pytest.mark.asyncio
async def test_reflect_lightweight_stores_json(memory_client):
    reflector = TradeReflector(
        memory_client=memory_client,
        deep_reflection_pnl_multiplier=2.0,
        deep_reflection_loss_multiplier=1.5,
        llm=None,
    )
    trade = make_closed_trade(
        pnl=Decimal("5.00"),
        expected_pnl=Decimal("6.00"),
        stop_loss=Decimal("-4.00"),
    )
    await reflector.reflect(trade, "test_agent")

    memory_client.store_private.assert_awaited_once()
    call_kwargs = memory_client.store_private.call_args.kwargs
    content = json.loads(call_kwargs["content"])
    assert content["symbol"] == "AAPL"
    assert content["outcome"] == "win"
    assert "AAPL" in call_kwargs["tags"]
    assert "win" in call_kwargs["tags"]


@pytest.mark.asyncio
async def test_reflect_does_not_trigger_deep_for_normal_pnl(memory_client):
    reflector = TradeReflector(
        memory_client=memory_client,
        deep_reflection_pnl_multiplier=2.0,
        deep_reflection_loss_multiplier=1.5,
        llm=None,
    )
    # pnl=5, expected=6 — NOT > 2x expected
    trade = make_closed_trade(
        pnl=Decimal("5.00"),
        expected_pnl=Decimal("6.00"),
        stop_loss=Decimal("-4.00"),
    )
    await reflector.reflect(trade, "test_agent")
    # store_private called once (lightweight only), no LLM
    assert memory_client.store_private.await_count == 1


@pytest.mark.asyncio
async def test_deep_reflection_triggered_when_pnl_exceeds_multiplier(memory_client):
    """abs(pnl)=15 > 2.0 × expected=6 → deep reflection fires."""
    reflector = TradeReflector(
        memory_client=memory_client,
        deep_reflection_loss_multiplier=1.5,
    )
    mock_llm_client = AsyncMock()
    mock_llm_client.complete = AsyncMock(
        return_value=MagicMock(
            text=(
                "What happened: AAPL surged on earnings beat.\n"
                "What triggered the signal: RSI breakout above 70.\n"
                "What worked: Momentum entry timed well.\n"
                "What I would do differently: N/A\n"
                "Market conditions at entry: Bullish, tech sector strong.\n"
                "Key lesson: Momentum works on earnings beats.\n"
                "Market observation: AAPL tends to run +3% on earnings beat days."
            )
        )
    )
    reflector._llm = mock_llm_client

    trade = make_closed_trade(
        pnl=Decimal("15.00"),
        expected_pnl=Decimal("6.00"),
        stop_loss=Decimal("-4.00"),
        outcome="win",
    )

    await reflector.reflect(trade, "test_agent")

    # lightweight + deep narrative + shared observation = 3 store calls
    assert memory_client.store_private.await_count == 2
    assert memory_client.store_shared.await_count == 1


@pytest.mark.asyncio
async def test_deep_reflection_triggered_on_large_loss(memory_client):
    """loss > 1.5 × stop_loss → deep reflection fires."""
    reflector = TradeReflector(
        memory_client=memory_client,
        deep_reflection_loss_multiplier=1.5,
    )
    mock_llm_client = AsyncMock()
    mock_llm_client.complete = AsyncMock(
        return_value=MagicMock(
            text=(
                "What happened: Stop blew through.\n"
                "What triggered the signal: Volume spike misread.\n"
                "What worked: N/A\n"
                "What I would do differently: Tighten stop earlier.\n"
                "Market conditions at entry: High volatility day.\n"
                "Key lesson: Wider stops in volatile regimes.\n"
                "Market observation: none"
            )
        )
    )
    reflector._llm = mock_llm_client

    trade = make_closed_trade(
        pnl=Decimal("-7.00"),
        expected_pnl=Decimal("-2.00"),
        stop_loss=Decimal("-4.00"),
        outcome="loss",
    )

    await reflector.reflect(trade, "test_agent")

    # lightweight + deep narrative; "none" observation → NOT stored to shared
    assert memory_client.store_private.await_count == 2
    assert memory_client.store_shared.await_count == 0


@pytest.mark.asyncio
async def test_query_returns_combined_results(memory_client):
    memory_client.search_both = AsyncMock(
        return_value=[
            {"value": "AAPL fades on volume", "tags": ["AAPL"]},
            {
                "value": "AAPL earnings beats run +3%",
                "tags": ["AAPL", "market_observation"],
            },
        ]
    )
    reflector = TradeReflector(
        memory_client=memory_client,
        deep_reflection_pnl_multiplier=2.0,
        deep_reflection_loss_multiplier=1.5,
        llm=None,
    )
    results = await reflector.query(
        "AAPL", "long breakout at 150", "test_agent", top_k=5
    )
    assert len(results) == 2
    memory_client.search_both.assert_awaited_once_with(
        "AAPL long breakout at 150", top_k=5
    )


@pytest.mark.asyncio
async def test_query_returns_empty_on_error(memory_client):
    memory_client.search_both = AsyncMock(side_effect=Exception("network error"))
    reflector = TradeReflector(
        memory_client=memory_client,
        deep_reflection_pnl_multiplier=2.0,
        deep_reflection_loss_multiplier=1.5,
        llm=None,
    )
    results = await reflector.query("AAPL", "long", "test_agent")
    assert results == []
