import aiosqlite
import pytest

from storage.db import init_db
from storage.pnl import TrackedPositionStore


@pytest.fixture
async def position_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield TrackedPositionStore(db)
    await db.close()


class TestTrackedPositionStore:
    async def test_open_and_get_position(self, position_store):
        position_id = await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-123",
            symbol="AAPL",
            side="long",
            entry_price="150.25",
            entry_quantity=100,
            entry_fees="10.50",
            entry_time="2026-03-25T10:00:00Z",
        )
        assert position_id == 1

        position = await position_store.get(position_id)
        assert position is not None
        assert position["agent_name"] == "trader_alpha"
        assert position["opportunity_id"] == "opp-123"
        assert position["symbol"] == "AAPL"
        assert position["side"] == "long"
        assert position["entry_price"] == "150.25"
        assert position["entry_quantity"] == 100
        assert position["entry_fees"] == "10.50"
        assert position["status"] == "open"

    async def test_open_position_persists_broker_and_account(self, position_store):
        position_id = await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-124",
            symbol="AAPL",
            side="long",
            entry_price="150.25",
            entry_quantity=100,
            entry_fees="10.50",
            entry_time="2026-03-25T10:00:00Z",
            broker_id="alpaca",
            account_id="acct-123",
        )

        position = await position_store.get(position_id)
        assert position is not None
        assert position["broker_id"] == "alpaca"
        assert position["account_id"] == "acct-123"

    async def test_close_position(self, position_store):
        position_id = await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-123",
            symbol="AAPL",
            side="long",
            entry_price="150.25",
            entry_quantity=100,
            entry_fees="10.50",
            entry_time="2026-03-25T10:00:00Z",
        )

        await position_store.close_position(
            position_id,
            exit_price="155.75",
            exit_fees="11.00",
            exit_time="2026-03-25T14:00:00Z",
            exit_reason="profit_target",
        )

        position = await position_store.get(position_id)
        assert position["status"] == "closed"
        assert position["exit_price"] == "155.75"
        assert position["exit_fees"] == "11.00"
        assert position["exit_time"] == "2026-03-25T14:00:00Z"
        assert position["exit_reason"] == "profit_target"

    async def test_list_open_positions(self, position_store):
        pos1 = await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-1",
            symbol="AAPL",
            side="long",
            entry_price="150.00",
            entry_quantity=100,
            entry_fees="10.00",
            entry_time="2026-03-25T09:00:00Z",
        )
        pos2 = await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-2",
            symbol="TSLA",
            side="short",
            entry_price="200.00",
            entry_quantity=50,
            entry_fees="15.00",
            entry_time="2026-03-25T10:00:00Z",
        )

        open_positions = await position_store.list_open()
        assert len(open_positions) == 2
        assert open_positions[0]["id"] == pos1
        assert open_positions[1]["id"] == pos2
        # Verify ordering by entry_time ASC
        assert open_positions[0]["entry_time"] < open_positions[1]["entry_time"]

    async def test_list_open_with_agent_filter(self, position_store):
        await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-1",
            symbol="AAPL",
            side="long",
            entry_price="150.00",
            entry_quantity=100,
            entry_fees="10.00",
            entry_time="2026-03-25T09:00:00Z",
        )
        await position_store.open_position(
            agent_name="trader_beta",
            opportunity_id="opp-2",
            symbol="TSLA",
            side="long",
            entry_price="200.00",
            entry_quantity=50,
            entry_fees="15.00",
            entry_time="2026-03-25T10:00:00Z",
        )

        alpha_positions = await position_store.list_open(agent_name="trader_alpha")
        assert len(alpha_positions) == 1
        assert alpha_positions[0]["agent_name"] == "trader_alpha"

    async def test_list_open_with_symbol_filter(self, position_store):
        await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-1",
            symbol="AAPL",
            side="long",
            entry_price="150.00",
            entry_quantity=100,
            entry_fees="10.00",
            entry_time="2026-03-25T09:00:00Z",
        )
        await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-2",
            symbol="TSLA",
            side="long",
            entry_price="200.00",
            entry_quantity=50,
            entry_fees="15.00",
            entry_time="2026-03-25T10:00:00Z",
        )

        aapl_positions = await position_store.list_open(symbol="AAPL")
        assert len(aapl_positions) == 1
        assert aapl_positions[0]["symbol"] == "AAPL"

    async def test_list_closed_by_agent(self, position_store):
        pos1 = await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-1",
            symbol="AAPL",
            side="long",
            entry_price="150.00",
            entry_quantity=100,
            entry_fees="10.00",
            entry_time="2026-03-25T09:00:00Z",
        )
        pos2 = await position_store.open_position(
            agent_name="trader_beta",
            opportunity_id="opp-2",
            symbol="TSLA",
            side="long",
            entry_price="200.00",
            entry_quantity=50,
            entry_fees="15.00",
            entry_time="2026-03-25T10:00:00Z",
        )

        await position_store.close_position(
            pos1,
            exit_price="155.00",
            exit_fees="11.00",
            exit_time="2026-03-25T14:00:00Z",
            exit_reason="profit_target",
        )
        await position_store.close_position(
            pos2,
            exit_price="195.00",
            exit_fees="16.00",
            exit_time="2026-03-25T15:00:00Z",
            exit_reason="stop_loss",
        )

        alpha_closed = await position_store.list_closed(agent_name="trader_alpha")
        assert len(alpha_closed) == 1
        assert alpha_closed[0]["id"] == pos1
        assert alpha_closed[0]["exit_reason"] == "profit_target"

    async def test_list_closed_ordering(self, position_store):
        pos1 = await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-1",
            symbol="AAPL",
            side="long",
            entry_price="150.00",
            entry_quantity=100,
            entry_fees="10.00",
            entry_time="2026-03-25T09:00:00Z",
        )
        pos2 = await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-2",
            symbol="TSLA",
            side="long",
            entry_price="200.00",
            entry_quantity=50,
            entry_fees="15.00",
            entry_time="2026-03-25T10:00:00Z",
        )

        await position_store.close_position(
            pos1,
            exit_price="155.00",
            exit_fees="11.00",
            exit_time="2026-03-25T14:00:00Z",
            exit_reason="profit_target",
        )
        await position_store.close_position(
            pos2,
            exit_price="195.00",
            exit_fees="16.00",
            exit_time="2026-03-25T15:00:00Z",
            exit_reason="stop_loss",
        )

        closed_positions = await position_store.list_closed()
        assert len(closed_positions) == 2
        # Verify ordering by exit_time DESC (most recent first)
        assert closed_positions[0]["exit_time"] > closed_positions[1]["exit_time"]

    async def test_update_max_adverse_excursion(self, position_store):
        position_id = await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-123",
            symbol="AAPL",
            side="long",
            entry_price="150.25",
            entry_quantity=100,
            entry_fees="10.50",
            entry_time="2026-03-25T10:00:00Z",
        )

        await position_store.update_mae(position_id, "2.50")

        position = await position_store.get(position_id)
        assert position["max_adverse_excursion"] == "2.50"

    async def test_get_open_quantity_by_symbol(self, position_store):
        await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-1",
            symbol="AAPL",
            side="long",
            entry_price="150.00",
            entry_quantity=100,
            entry_fees="10.00",
            entry_time="2026-03-25T09:00:00Z",
        )
        await position_store.open_position(
            agent_name="trader_alpha",
            opportunity_id="opp-2",
            symbol="AAPL",
            side="long",
            entry_price="151.00",
            entry_quantity=50,
            entry_fees="5.00",
            entry_time="2026-03-25T10:00:00Z",
        )
        await position_store.open_position(
            agent_name="trader_beta",
            opportunity_id="opp-3",
            symbol="TSLA",
            side="short",
            entry_price="200.00",
            entry_quantity=75,
            entry_fees="15.00",
            entry_time="2026-03-25T11:00:00Z",
        )

        quantities = await position_store.get_open_quantity_by_symbol()
        assert quantities["AAPL"] == 150  # 100 + 50
        assert quantities["TSLA"] == 75

    async def test_get_open_quantity_by_symbol_no_open_positions(self, position_store):
        quantities = await position_store.get_open_quantity_by_symbol()
        assert quantities == {}

    async def test_get_nonexistent_position(self, position_store):
        position = await position_store.get(999)
        assert position is None
