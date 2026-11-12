"""The transaction machinery is its own module; stores hold one, they are not one."""

import aiosqlite
import pytest

from storage.exit_rules import ExitRuleStore
from storage.paper import PaperStore
from storage.pnl import TrackedPositionStore
from storage.unit_of_work import PaperWriteNotStarted, UnitOfWork


@pytest.fixture
async def db():
    connection = await aiosqlite.connect(":memory:")
    connection.row_factory = aiosqlite.Row
    try:
        yield connection
    finally:
        await connection.close()


def test_other_stores_are_not_paper_ledgers():
    assert not issubclass(TrackedPositionStore, PaperStore)
    assert not issubclass(ExitRuleStore, PaperStore)


async def test_transaction_commits_and_is_reentrant_for_its_owner(db):
    work = UnitOfWork(db)
    async with work.transaction() as outer:
        await outer.execute("CREATE TABLE t (v INTEGER)")
        async with work.transaction() as inner:
            assert inner is outer
            await inner.execute("INSERT INTO t VALUES (1)")
        assert db.in_transaction
        assert await work.handle() is outer
    assert not db.in_transaction
    row = await (await db.execute("SELECT v FROM t")).fetchone()
    assert row["v"] == 1


async def test_failure_rolls_back_only_its_own_work(db):
    await db.execute("CREATE TABLE t (v INTEGER)")
    await db.commit()
    work = UnitOfWork(db)
    with pytest.raises(ValueError):
        async with work.transaction() as handle:
            await handle.execute("INSERT INTO t VALUES (1)")
            raise ValueError("boom")
    assert await (await db.execute("SELECT v FROM t")).fetchone() is None


async def test_unrelated_open_transaction_is_a_definite_non_start(db):
    await db.execute("CREATE TABLE t (v INTEGER)")
    await db.execute("INSERT INTO t VALUES (1)")
    assert db.in_transaction
    with pytest.raises(PaperWriteNotStarted):
        async with UnitOfWork(db).transaction():
            pass
    assert db.in_transaction


async def test_stores_sharing_a_unit_of_work_share_its_transaction(db):
    work = UnitOfWork(db)
    ledger = PaperStore(unit_of_work=work)
    async with work.transaction() as handle:
        assert await ledger._get_db() is handle


async def test_memory_database_keeps_its_connection(db):
    work = UnitOfWork(db)
    assert await work.adopt_dedicated_connection(busy_timeout=True) is None
    assert not work.owns_connection
    assert await work.handle() is db


async def test_file_database_gets_a_dedicated_connection(tmp_path):
    shared = await aiosqlite.connect(tmp_path / "ledger.db")
    work = UnitOfWork(shared)
    try:
        own = await work.adopt_dedicated_connection(busy_timeout=True)
        assert own is not None and own is not shared
        assert work.owns_connection
        assert await work.handle() is own
        assert await work.adopt_dedicated_connection(busy_timeout=True) is None
    finally:
        await work.close()
        await shared.close()


async def test_store_without_a_database_resolves_its_transaction_handle(db, monkeypatch):
    async def fallback():
        return db

    monkeypatch.setattr("storage.db.get_db", fallback)
    work = UnitOfWork()
    async with work.transaction() as handle:
        assert handle is db
        assert await work.handle() is handle


def test_a_store_takes_a_database_or_a_unit_of_work_not_both(db):
    with pytest.raises(ValueError):
        PaperStore(db, unit_of_work=UnitOfWork(db))


async def test_failed_adoption_is_retried_by_the_exit_rule_store(tmp_path, monkeypatch):
    shared = await aiosqlite.connect(tmp_path / "rules.db")
    shared.row_factory = aiosqlite.Row
    store = ExitRuleStore(shared)
    real = UnitOfWork.adopt_dedicated_connection

    async def fail_once(self, *args, **kwargs):
        monkeypatch.setattr(UnitOfWork, "adopt_dedicated_connection", real)
        raise OSError("disk unavailable")

    monkeypatch.setattr(UnitOfWork, "adopt_dedicated_connection", fail_once)
    try:
        with pytest.raises(OSError):
            await store.sync_position(1, [])
        assert store._sync_store is None
    finally:
        await store.close()
        await shared.close()
