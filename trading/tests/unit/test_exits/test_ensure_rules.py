"""Exit protection publication is durable and reconciliation retries are idempotent."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from exits.manager import ExitManager
from exits.rules import StopLoss, TrailingStop
from storage.exit_rules import ExitRuleStore


@pytest.fixture
async def store():
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "CREATE TABLE position_exit_rules (position_id INTEGER PRIMARY KEY, rules_json TEXT NOT NULL)"
        )
        await db.commit()
        yield ExitRuleStore(db)


async def test_ensure_preserves_cached_trailing_peak_on_repeated_fill_reconciliation(
    store,
):
    manager = ExitManager(store)
    await manager.ensure_rules(7, [TrailingStop(Decimal("0.05"))])
    manager.update_trailing(7, Decimal("130"))
    cached = manager._rules[7][0]
    await manager.ensure_rules(7, [TrailingStop(Decimal("0.10"))])
    assert manager._rules[7][0] is cached
    assert cached._peak == Decimal("130")
    assert manager.check(7, Decimal("120")) is cached


async def test_ensure_restores_existing_durable_rules_without_overwriting(store):
    trail = TrailingStop(Decimal("0.05"))
    trail.update(Decimal("125"))
    await store.save(7, [trail.to_dict()])
    manager = ExitManager(store)
    await manager.ensure_rules(7, [StopLoss(Decimal("50"))])
    assert isinstance(manager._rules[7][0], TrailingStop)
    assert manager._rules[7][0]._peak == Decimal("125")
    assert (await store.load_all())[7] == [trail.to_dict()]


async def test_ensure_failure_after_durable_insert_retries_without_replacing(store):
    manager = ExitManager(store)
    original = store.ensure

    async def interrupted(position_id, rules):
        await original(position_id, rules)
        raise ConnectionError("receipt unavailable after commit")

    store.ensure = interrupted
    with pytest.raises(ConnectionError):
        await manager.ensure_rules(7, [StopLoss(Decimal("95"))])
    assert 7 not in manager._rules
    store.ensure = original
    await manager.ensure_rules(7, [StopLoss(Decimal("80"))])
    assert manager._rules[7][0].stop_price == Decimal("95")


async def test_concurrent_store_ensure_has_one_durable_winner(tmp_path):
    path = str(tmp_path / "exit-rules.db")
    async with aiosqlite.connect(path) as first, aiosqlite.connect(path) as second:
        first.row_factory = second.row_factory = aiosqlite.Row
        await first.execute(
            "CREATE TABLE position_exit_rules (position_id INTEGER PRIMARY KEY, rules_json TEXT NOT NULL)"
        )
        await first.commit()
        managers = [
            ExitManager(ExitRuleStore(first)),
            ExitManager(ExitRuleStore(second)),
        ]
        await asyncio.gather(
            managers[0].ensure_rules(7, [StopLoss(Decimal("95"))]),
            managers[1].ensure_rules(7, [StopLoss(Decimal("80"))]),
        )
        assert (
            managers[0]._rules[7][0].stop_price == managers[1]._rules[7][0].stop_price
        )
        assert len(await ExitRuleStore(first).load_all()) == 1


async def test_empty_durable_rules_are_not_overwritten_on_retry(store):
    manager = ExitManager(store)
    await manager.ensure_rules(7, [])
    await manager.ensure_rules(7, [StopLoss(Decimal("95"))])
    assert manager._rules[7] == []
    restarted = ExitManager(store)
    await restarted.ensure_rules(7, [StopLoss(Decimal("80"))])
    assert restarted._rules[7] == []


async def test_attach_failed_persistence_keeps_existing_cache(store):
    manager = ExitManager(store)
    await manager.attach(7, [StopLoss(Decimal("95"))])
    store.save = AsyncMock(side_effect=ConnectionError("offline"))
    with pytest.raises(ConnectionError):
        await manager.attach(7, [StopLoss(Decimal("80"))])
    assert manager.check(7, Decimal("90")) is manager._rules[7][0]
    assert manager._rules[7][0].stop_price == Decimal("95")


async def test_detach_failed_persistence_retains_active_exit_protection(store):
    manager = ExitManager(store)
    await manager.attach(7, [StopLoss(Decimal("95"))])
    store.delete = AsyncMock(side_effect=ConnectionError("offline"))
    with pytest.raises(ConnectionError):
        await manager.detach(7)
    assert manager.check(7, Decimal("90")) is not None
    assert 7 in await store.load_all()


async def test_attach_does_not_publish_before_persistence_completes():
    from types import SimpleNamespace

    started, release = asyncio.Event(), asyncio.Event()

    async def save(position_id, rules):
        started.set()
        await release.wait()

    manager = ExitManager(SimpleNamespace(save=save))
    task = asyncio.create_task(manager.attach(7, [StopLoss(Decimal("95"))]))
    await started.wait()
    assert manager.check(7, Decimal("90")) is None
    release.set()
    await task
    assert manager.check(7, Decimal("90")) is not None


async def _position_table(db):
    await db.execute("CREATE TABLE tracked_positions (id INTEGER PRIMARY KEY, status TEXT)")
    await db.execute("INSERT INTO tracked_positions VALUES (7, 'open')")
    await db.commit()


async def test_reconcile_closed_position_cannot_be_reattached_by_stale_entry(store):
    await _position_table(store._db)
    manager = ExitManager(store)
    await manager.reconcile_position(7, [TrailingStop(Decimal('0.05'))])
    manager.update_trailing(7, Decimal('130'))
    cached = manager._rules[7][0]
    await manager.reconcile_position(7, [])
    assert manager._rules[7][0] is cached
    assert cached._peak == Decimal('130')
    await store._db.execute("UPDATE tracked_positions SET status='closed' WHERE id=7")
    await store._db.commit()
    # A stale entry's defaults must not resurrect protection after a full exit.
    await manager.reconcile_position(7, [StopLoss(Decimal('95'))])
    await ExitManager(store).reconcile_position(7, [StopLoss(Decimal('80'))])
    assert 7 not in manager._rules
    assert await store.load_all() == {}


async def test_reconcile_commit_receipt_failure_retry_uses_durable_winner(store):
    await _position_table(store._db)
    manager = ExitManager(store)
    original = store.sync_position

    async def interrupted(position_id, rules):
        await original(position_id, rules)
        raise ConnectionError('lost receipt')

    store.sync_position = interrupted
    with pytest.raises(ConnectionError):
        await manager.reconcile_position(7, [StopLoss(Decimal('95'))])
    assert 7 not in manager._rules
    store.sync_position = original
    await manager.reconcile_position(7, [StopLoss(Decimal('80'))])
    assert manager._rules[7][0].stop_price == Decimal('95')


async def test_reconcile_failure_does_not_remove_cached_protection(store):
    await _position_table(store._db)
    manager = ExitManager(store)
    await manager.reconcile_position(7, [StopLoss(Decimal('95'))])
    store.sync_position = AsyncMock(side_effect=ConnectionError('offline'))
    with pytest.raises(ConnectionError):
        await manager.reconcile_position(7, [])
    assert manager.check(7, Decimal('90')) is not None


async def test_reconcile_uses_owned_connection_and_does_not_commit_callers_work(tmp_path):
    path = str(tmp_path / 'sync.db')
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute('CREATE TABLE position_exit_rules (position_id INTEGER PRIMARY KEY, rules_json TEXT)')
        await _position_table(db)
        store = ExitRuleStore(db)
        try:
            await store.sync_position(7, [StopLoss(Decimal('95')).to_dict()])
            assert store._sync_store._db is not db
            await db.execute('BEGIN')
            await store.sync_position(7, [])
            assert db.in_transaction
            await db.rollback()
            await db.execute("UPDATE tracked_positions SET status='closed' WHERE id=7")
            await db.commit()
            assert await store.sync_position(7, [StopLoss(Decimal('80')).to_dict()]) is None
            assert await store.load_all() == {}
        finally:
            await store.close()
        assert (await (await db.execute('SELECT 1')).fetchone())[0] == 1
        with pytest.raises(RuntimeError, match='closed'):
            await store.sync_position(7, [])


async def test_hydration_keeps_advanced_local_trailing_state(store):
    manager = ExitManager(store)
    await manager.ensure_rules(7, [TrailingStop(Decimal('0.05'))])
    manager.update_trailing(7, Decimal('130'))
    cached = manager._rules[7][0]
    store.load_all = AsyncMock(side_effect=AssertionError('must not reload cached rules'))
    assert await manager.hydrate_rules(7) is True
    assert manager._rules[7][0] is cached
    assert cached._peak == Decimal('130')
