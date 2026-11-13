"""Readiness deadlines and read-only behavior through the owned session."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from config import Config
from storage.readiness import StorageSession, StorageUnavailable
from storage.paper import PaperStore
from storage.pnl import TrackedPositionStore


async def test_check_does_not_write_or_repeat_initialization():
    async with StorageSession(
        Config(db_path=":memory:", paper_trading=False)
    ) as session:
        statements = []
        await session.db.set_trace_callback(statements.append)
        await session.certify()
        assert (await session.check()).ready
        assert (await session.check()).ready
        assert statements and all(sql.startswith("SELECT ") for sql in statements)


async def test_slow_database_is_bounded_and_can_recover(monkeypatch):
    async with StorageSession(
        Config(db_path=":memory:", paper_trading=False), timeout_seconds=0.25
    ) as session:
        execute = session.db.execute

        @asynccontextmanager
        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(1)
            async with execute(*args, **kwargs) as cursor:
                yield cursor

        with monkeypatch.context() as delayed:
            delayed.setattr(session.db, "execute", slow_execute)
            with pytest.raises(StorageUnavailable) as caught:
                await session.certify()
            assert caught.value.report.issues[0].error_type == "TimeoutError"
        await session.certify()
        assert (await session.check()).ready

        with monkeypatch.context() as delayed:
            delayed.setattr(session.db, "execute", slow_execute)
            report = await session.check()
            assert not report.ready
            assert report.issues[0].error_type == "TimeoutError"
        assert (await session.check()).ready


async def test_failed_probe_never_exposes_driver_message(monkeypatch):
    async with StorageSession(
        Config(db_path=":memory:", paper_trading=False)
    ) as session:

        @asynccontextmanager
        async def refused(*args, **kwargs):
            raise RuntimeError("private credential or stored data")
            yield  # pragma: no cover

        monkeypatch.setattr(session.db, "execute", refused)
        with pytest.raises(StorageUnavailable) as caught:
            await session.certify()
        assert "private" not in str(caught.value)
        assert "private" not in repr(caught.value.report)


@pytest.mark.parametrize("owner", [PaperStore, TrackedPositionStore])
async def test_unbound_inspection_never_initializes_default_storage(monkeypatch, owner):
    async def forbidden(*args, **kwargs):
        pytest.fail("Readiness must not acquire or initialize default storage")

    monkeypatch.setattr("storage.db.get_db", forbidden)
    store = owner(None)
    issues = await store.check_storage()
    assert issues and issues[0].error_type == "Unavailable"
    await store.close()
    assert (await store.check_storage())[0].error_type == "Unavailable"


@pytest.mark.parametrize("owner", [PaperStore, TrackedPositionStore])
async def test_unsupported_transaction_implementation_is_unready(owner):
    store = owner(object())
    issues = await store.check_storage()
    assert issues and issues[0].error_type == "UnsupportedTransactions"
    await store.close()
