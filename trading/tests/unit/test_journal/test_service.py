"""Tests for JournalService."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock


def _make_closed_position(**overrides):
    base = {
        "id": 42,
        "agent_name": "rsi_scanner",
        "symbol": "AAPL",
        "side": "buy",
        "entry_price": "100.00",
        "exit_price": "110.00",
        "entry_quantity": 10,
        "entry_fees": "2.00",
        "exit_fees": "2.00",
        "entry_time": "2026-03-24T14:30:00",
        "exit_time": "2026-03-26T09:15:00",
        "opportunity_id": "opp-1",
        "max_adverse_excursion": "-8.00",
        "exit_reason": "take_profit",
        "status": "closed",
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_pnl_store():
    store = MagicMock()
    store.list_closed = AsyncMock(
        return_value=[
            _make_closed_position(id=1, agent_name="rsi_scanner", symbol="AAPL"),
            _make_closed_position(
                id=2,
                agent_name="volume_spike",
                symbol="TSLA",
                entry_price="200.00",
                exit_price="190.00",
                side="buy",
            ),
            _make_closed_position(
                id=3,
                agent_name="rsi_scanner",
                symbol="MSFT",
                entry_price="50.00",
                exit_price="55.00",
            ),
        ]
    )
    return store


@pytest.fixture
def mock_opp_store():
    store = MagicMock()
    store.get = AsyncMock(return_value=None)
    return store


@pytest.fixture
def mock_autopsy():
    gen = MagicMock()
    gen.get_or_generate = AsyncMock(return_value="Trade worked because of momentum.")
    gen.get_cached = AsyncMock(return_value=None)
    return gen


@pytest.mark.asyncio
async def test_list_trades_returns_journal_entries(
    mock_pnl_store, mock_opp_store, mock_autopsy
):
    from journal.service import JournalService

    svc = JournalService(
        pnl_store=mock_pnl_store, opp_store=mock_opp_store, autopsy=mock_autopsy
    )
    entries = await svc.list_trades(limit=5)
    assert len(entries) == 3
    assert entries[0].position_id == 1
    assert entries[0].symbol == "AAPL"


@pytest.mark.asyncio
async def test_pnl_computation_buy(mock_pnl_store, mock_opp_store, mock_autopsy):
    """Entry $100, exit $110, qty 10, buy, fees $2+$2 → P&L = $96.00"""
    from journal.service import JournalService

    svc = JournalService(
        pnl_store=mock_pnl_store, opp_store=mock_opp_store, autopsy=mock_autopsy
    )
    entries = await svc.list_trades(limit=5)
    aapl = entries[0]
    assert aapl.pnl == Decimal("96.00")
    assert round(aapl.pnl_pct, 1) == 9.6


@pytest.mark.asyncio
async def test_pnl_computation_losing_trade(
    mock_pnl_store, mock_opp_store, mock_autopsy
):
    """Entry $200, exit $190, qty 10, buy → gross = -$100, fees $4 → P&L = -$104.00"""
    from journal.service import JournalService

    svc = JournalService(
        pnl_store=mock_pnl_store, opp_store=mock_opp_store, autopsy=mock_autopsy
    )
    entries = await svc.list_trades(limit=5)
    tsla = entries[1]
    assert tsla.pnl == Decimal("-104.00")


@pytest.mark.asyncio
async def test_get_trade_detail_includes_autopsy(
    mock_pnl_store, mock_opp_store, mock_autopsy
):
    from journal.service import JournalService

    mock_pnl_store.get = AsyncMock(return_value=_make_closed_position(id=42))
    svc = JournalService(
        pnl_store=mock_pnl_store, opp_store=mock_opp_store, autopsy=mock_autopsy
    )
    detail = await svc.get_trade_detail(42)
    assert detail is not None
    assert detail.autopsy == "Trade worked because of momentum."
    assert detail.entry_price == Decimal("100.00")


@pytest.mark.asyncio
async def test_agent_filter(mock_pnl_store, mock_opp_store, mock_autopsy):
    from journal.service import JournalService

    svc = JournalService(
        pnl_store=mock_pnl_store, opp_store=mock_opp_store, autopsy=mock_autopsy
    )
    await svc.list_trades(agent_name="rsi_scanner")
    mock_pnl_store.list_closed.assert_awaited_with(agent_name="rsi_scanner", limit=5)
