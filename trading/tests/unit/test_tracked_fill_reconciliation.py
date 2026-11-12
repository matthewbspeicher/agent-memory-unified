from decimal import Decimal as D
import aiosqlite
import pytest
from storage.db import init_db
from storage.pnl import TrackedPositionStore


@pytest.fixture
async def store(tmp_path):
    async with aiosqlite.connect(tmp_path / "tracked.db") as db:
        db.row_factory = aiosqlite.Row
        await init_db(db)
        value = TrackedPositionStore(db)
        try:
            yield value, db
        finally:
            await value.close()


async def entry(store, quantity="0.5", price="100", fees="1"):
    return await store.apply_entry_fill(
        broker_id="paper",
        account_id="PAPER",
        order_id="entry",
        cumulative_quantity=quantity,
        cumulative_avg_price=price,
        cumulative_fees=fees,
        filled_at="2026-11-11T15:00:00+00:00",
        agent_name="agent",
        opportunity_id="opp",
        symbol="TEST",
        side="long",
    )


async def exit_fill(store, position, quantity, price="110", fees="1", order_id="exit"):
    return await store.apply_exit_fill(
        position["id"],
        broker_id="paper",
        account_id="PAPER",
        order_id=order_id,
        cumulative_quantity=quantity,
        cumulative_avg_price=price,
        cumulative_fees=fees,
        filled_at="2026-11-11T16:00:00+00:00",
        exit_reason="target",
    )


async def test_fractional_cumulative_replay_partial_exit_and_restart(store):
    value, db = store
    row = await entry(value)
    assert row["entry_quantity"] == D(".5")
    assert await entry(value) == row
    row = await entry(value, "1.25", "102", "2")
    assert row["entry_quantity"] == D("1.25")
    assert row["entry_price"] == "102"
    row = await exit_fill(value, row, ".25")
    assert row["status"] == "open"
    assert D(row["remaining_quantity"]) == 1
    assert D(row["realized_pnl"]) == D(".6")
    assert await exit_fill(value, row, ".25") == row
    restarted = TrackedPositionStore(db)
    try:
        row = await exit_fill(restarted, row, "1.25", "112", "2")
        assert row["status"] == "closed"
        assert D(row["remaining_quantity"]) == 0
        assert D(row["realized_pnl"]) == D("8.5")
        assert D(row["exit_price"]) == 112
    finally:
        await restarted.close()


@pytest.mark.parametrize(
    "quantity,price,fees",
    [("0.25", "100", "1"), (".5", "101", "1"), (".5", "100", "2"), ("1", "100", "0")],
)
async def test_out_of_order_or_conflicting_entry_rejected(store, quantity, price, fees):
    value, _ = store
    before = await entry(value)
    with pytest.raises(ValueError):
        await entry(value, quantity, price, fees)
    assert await value.get(before["id"]) == before


async def test_over_exit_rolls_back_receipt_and_position(store):
    value, _ = store
    before = await entry(value)
    with pytest.raises(ValueError, match="exceeds"):
        await exit_fill(value, before, "1")
    assert await value.get(before["id"]) == before
    row = await exit_fill(value, before, ".5")
    assert row["status"] == "closed"


async def test_owned_connection_does_not_commit_unrelated_work(store):
    value, db = store
    await value.init_tables()
    await db.execute(
        "INSERT INTO tracked_positions(agent_name,opportunity_id,symbol,side,entry_price,entry_quantity,entry_time) VALUES('alien','alien','ALIEN','long','1','1','now')"
    )
    own = await value._get_db()
    await own.execute("PRAGMA busy_timeout=1")
    with pytest.raises(RuntimeError):
        await entry(value)
    assert db.in_transaction
    await db.rollback()
    assert await value.list_open() == []


async def test_pending_execution_includes_entry_and_exit(store):
    value, _ = store
    row = await entry(value)
    assert not await value.has_pending_execution(row["id"])
    async with value.transaction() as db:
        await db.execute(
            "CREATE TABLE paper_fill_jobs(job_id TEXT,position_id INTEGER,role TEXT,done INTEGER)"
        )
        await db.execute(
            "INSERT INTO paper_fill_jobs VALUES('job',?,'entry',0)", (row["id"],)
        )
    assert await value.has_pending_execution(row["id"])
    async with value.transaction() as db:
        await db.execute("UPDATE paper_fill_jobs SET done=1")
    assert not await value.has_pending_execution(row["id"])


async def test_postgres_migration_and_insert_share_bound_transaction():
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock
    from storage.postgres import PostgresDB

    connection = AsyncMock()
    connection.fetch.return_value = []
    connection.fetchrow.return_value = {"id": 7}

    @asynccontextmanager
    async def transaction():
        yield

    connection.transaction = transaction

    class Pool:
        @asynccontextmanager
        async def acquire(self, **kwargs):
            yield connection

    value = TrackedPositionStore(PostgresDB(Pool()))
    result = await value.open_position(
        agent_name="agent",
        opportunity_id="opp",
        symbol="X",
        side="long",
        entry_price="1",
        entry_quantity=D("0.123456789123456789"),
        entry_fees="0",
        entry_time="now",
    )
    assert result == 7
    statements = [call.args[0] for call in connection.execute.call_args_list]
    assert any("ALTER COLUMN entry_quantity TYPE TEXT" in sql for sql in statements)
    assert any(
        "pg_advisory_xact_lock" in call.args[0]
        for call in connection.fetch.call_args_list
    )
    args = connection.fetchrow.call_args.args
    assert args[6] == "0.123456789123456789"
    assert args[-1] == "0.123456789123456789"


async def test_pending_entry_blocks_during_projection_link_gap(store):
    value, _ = store
    row = await entry(value)
    async with value.transaction() as db:
        await db.execute(
            "CREATE TABLE paper_fill_jobs(job_id TEXT,position_id INTEGER,role TEXT,done INTEGER)"
        )
        await db.execute("INSERT INTO paper_fill_jobs VALUES('opp',NULL,'entry',0)")
    assert await value.has_pending_execution(row["id"])


@pytest.mark.parametrize("actual_epoch", ["reset-generation", None])
async def test_stale_epoch_cannot_project_entry(store, actual_epoch):
    value, _ = store
    await value.init_tables()
    async with value.transaction() as db:
        await db.execute(
            "CREATE TABLE paper_risk_coverage(account_id TEXT PRIMARY KEY,generation TEXT)"
        )
        if actual_epoch:
            await db.execute(
                "INSERT INTO paper_risk_coverage VALUES(?,?)", ("PAPER", actual_epoch)
            )
    with pytest.raises(ValueError, match="generation changed"):
        await value.apply_entry_fill(
            broker_id="paper",
            account_id="PAPER",
            order_id="entry",
            cumulative_quantity=".5",
            cumulative_avg_price="100",
            cumulative_fees="1",
            filled_at="now",
            agent_name="agent",
            opportunity_id="opp",
            symbol="TEST",
            side="long",
            expected_epoch="old-generation",
        )
    assert await value.list_open() == []
    async with value.transaction() as db:
        assert not await (
            await db.execute("SELECT * FROM tracked_fill_receipts")
        ).fetchall()


async def test_stale_epoch_cannot_project_exit(store):
    value, _ = store
    before = await entry(value)
    async with value.transaction() as db:
        await db.execute(
            "CREATE TABLE paper_risk_coverage(account_id TEXT PRIMARY KEY,generation TEXT)"
        )
        await db.execute("INSERT INTO paper_risk_coverage VALUES('PAPER','new')")
    with pytest.raises(ValueError, match="generation changed"):
        await value.apply_exit_fill(
            before["id"],
            broker_id="paper",
            account_id="PAPER",
            order_id="exit",
            cumulative_quantity=".5",
            cumulative_avg_price="110",
            cumulative_fees="1",
            filled_at="now",
            exit_reason="target",
            expected_epoch="old",
        )
    assert await value.get(before["id"]) == before
    async with value.transaction() as db:
        assert not await (
            await db.execute("SELECT * FROM tracked_fill_receipts WHERE role='exit'")
        ).fetchall()
