"""Durable offer/metadata concurrency on SQLite, PostgreSQL TEXT and JSONB.

Each interleaving uses a second store and the database's real conditional
UPDATE. No process-local mutex or database clock precision is assumed.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import aiosqlite
import asyncpg
import pytest

from agents.approval import ApprovalRefused, OpportunityApprover
from agents.models import Opportunity, OpportunityStatus
from broker.models import LimitOrder, OrderSide, Symbol, TIF
from storage.opportunities import (
    APPROVABLE_KEY,
    BROKER_KEY,
    EXIT_KEY,
    ORDER_TERMS_KEY,
    REVISION_KEY,
    OpportunityStore,
)
from storage.postgres import PostgresDB

pytestmark = pytest.mark.integration


@pytest.fixture(params=["sqlite", "postgres-text", "postgres-jsonb"])
async def store(request, tmp_path):
    ddl = """CREATE TABLE opportunities (
        id TEXT PRIMARY KEY, agent_name TEXT NOT NULL, symbol TEXT NOT NULL,
        signal TEXT NOT NULL, confidence REAL NOT NULL, reasoning TEXT NOT NULL,
        suggested_trade TEXT, status TEXT NOT NULL, expires_at TEXT,
        data DATA_TYPE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    if request.param == "sqlite":
        db = await aiosqlite.connect(tmp_path / "opportunities.db")
        db.row_factory = aiosqlite.Row
        await db.execute(ddl.replace("DATA_TYPE", "TEXT"))
        await db.commit()
        try:
            yield OpportunityStore(db)
        finally:
            await db.close()
    else:
        dsn = os.environ["AMU_TEST_POSTGRES_DSN"]
        schema = "revision_" + uuid4().hex
        admin = await asyncpg.connect(dsn)
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = None
        try:
            pool = await asyncpg.create_pool(
                dsn,
                min_size=2,
                max_size=4,
                server_settings={"search_path": schema, "timezone": "Asia/Tokyo"},
            )
            db = PostgresDB(pool)
            await db.execute(
                ddl.replace(
                    "DATA_TYPE", "JSONB" if request.param.endswith("jsonb") else "TEXT"
                )
            )
            yield OpportunityStore(db)
        finally:
            if pool:
                await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()


@pytest.fixture
async def writer(store):
    if isinstance(store._db, PostgresDB):
        yield OpportunityStore(store._db)  # pool operations use independent sessions
    else:
        row = await (await store._db.execute("PRAGMA database_list")).fetchone()
        db = await aiosqlite.connect(row["file"])
        db.row_factory = aiosqlite.Row
        try:
            yield OpportunityStore(db)
        finally:
            await db.close()


def opportunity(quantity="5", *, is_exit=False, broker_id="paper"):
    symbol = Symbol("TEST")
    return Opportunity(
        id="revision-test",
        agent_name="test",
        symbol=symbol,
        signal="test",
        confidence=1,
        reasoning="test",
        data={"edge": "0.1"},
        timestamp=datetime.now(timezone.utc),
        suggested_trade=LimitOrder(
            symbol,
            OrderSide.BUY,
            Decimal(quantity),
            "PAPER",
            TIF.GTC,
            limit_price=Decimal("99"),
        ),
        broker_id=broker_id,
        is_exit=is_exit,
        _exit_fraction=0.5 if is_exit else 1,
    )


async def offer(store, opp):
    assert await store.save(opp)
    assert await store.mark_approvable(opp.id, revision=opp.data[REVISION_KEY])


def after_read(store, callback):
    read = store._read_metadata

    async def interleave(oid):
        row = await read(oid)
        store._read_metadata = read
        await callback()
        return row

    store._read_metadata = interleave


async def assert_current(store, opp):
    loaded = await store.load(opp.id)
    row = await store.get(opp.id)
    assert loaded.suggested_trade.quantity == opp.suggested_trade.quantity
    assert json.loads(row["suggested_trade"])["quantity"] == str(
        loaded.suggested_trade.quantity
    )
    assert loaded.broker_id == opp.broker_id
    assert loaded.is_exit == opp.is_exit
    assert loaded._exit_fraction == opp._exit_fraction
    assert loaded.data[REVISION_KEY] == opp.data[REVISION_KEY]
    return loaded


async def test_revision_survives_restart_changes_on_every_save_and_cannot_be_forged(
    store,
):
    first = opportunity()
    first.data[REVISION_KEY] = "agent-supplied"
    await store.save(first)
    first_revision = first.data[REVISION_KEY]
    assert first_revision != "agent-supplied"
    reopened = OpportunityStore(store._db)
    assert (await reopened.load(first.id)).data[REVISION_KEY] == first_revision
    await reopened.save(first)  # even identical visible terms need a new offer
    assert first.data[REVISION_KEY] != first_revision
    assert not await store.mark_approvable(first.id, revision=first_revision)
    assert await reopened.mark_approvable(first.id, revision=first.data[REVISION_KEY])


async def test_stale_router_cannot_offer_a_replacement_already_present_before_its_read(
    store, writer
):
    first, replacement = (
        opportunity(),
        opportunity("500", is_exit=True, broker_id="secondary"),
    )
    await store.save(first)
    await writer.save(replacement)
    assert not await store.mark_approvable(first.id, revision=first.data[REVISION_KEY])
    await assert_current(store, replacement)
    assert not await store.is_approvable(first.id)


async def test_offer_racing_replacement_cannot_restore_old_terms_even_with_equal_timestamps(
    store, writer
):
    first, replacement = (
        opportunity(),
        opportunity("500", is_exit=True, broker_id="secondary"),
    )
    await store.save(first)

    async def replace():
        # Deterministic clock collision, including on PostgreSQL. Only audit
        # timestamps are pinned; the executable terms are produced by save().
        old_time = (await store.get(first.id))["updated_at"]
        await writer.save(replacement)
        await store._db.execute(
            "UPDATE opportunities SET updated_at=? WHERE id=?", (old_time, first.id)
        )
        await store._db.commit()

    after_read(store, replace)
    assert not await store.mark_approvable(first.id, revision=first.data[REVISION_KEY])
    await assert_current(store, replacement)
    assert not await store.is_approvable(first.id)


async def test_offer_retries_a_metadata_conflict_without_losing_the_patch(
    store, writer
):
    opp = opportunity()
    await store.save(opp)
    after_read(store, lambda: writer.update_data(opp.id, {"new_note": "keep"}))
    assert await store.mark_approvable(opp.id, revision=opp.data[REVISION_KEY])
    assert (await assert_current(store, opp)).data["new_note"] == "keep"
    assert await store.is_approvable(opp.id)


@pytest.mark.parametrize("bound", [True, False])
async def test_patch_racing_replacement_never_restores_old_control_metadata(
    store, writer, bound
):
    first, replacement = (
        opportunity(),
        opportunity("500", is_exit=True, broker_id="secondary"),
    )
    await offer(store, first)
    after_read(store, lambda: offer(writer, replacement))
    kwargs = {"revision": first.data[REVISION_KEY]} if bound else {}
    changed = await store.update_data(
        first.id, {"old_note": "stale", ORDER_TERMS_KEY: "forged"}, **kwargs
    )
    assert changed is (not bound)
    loaded = await assert_current(store, replacement)
    assert ("old_note" in loaded.data) is (not bound)
    assert await store.is_approvable(first.id)


async def test_metadata_patch_cannot_erase_a_new_offer(store, writer):
    opp = opportunity()
    await store.save(opp)
    after_read(
        store, lambda: writer.mark_approvable(opp.id, revision=opp.data[REVISION_KEY])
    )
    assert await store.update_data(
        opp.id, {"note": "keep"}, revision=opp.data[REVISION_KEY]
    )
    assert await store.is_approvable(opp.id)
    assert (await assert_current(store, opp)).data["note"] == "keep"


async def test_disjoint_concurrent_metadata_patches_both_survive(store, writer):
    opp = opportunity()
    await offer(store, opp)
    after_read(
        store,
        lambda: writer.update_data(
            opp.id,
            {"execution_receipt": {"order_id": "confirmed"}},
            revision=opp.data[REVISION_KEY],
        ),
    )
    assert await store.update_data(
        opp.id,
        {"confidence_calibration": {"score": 1}},
        revision=opp.data[REVISION_KEY],
    )
    loaded = await assert_current(store, opp)
    assert loaded.data["execution_receipt"] == {"order_id": "confirmed"}
    assert loaded.data["confidence_calibration"] == {"score": 1}
    assert loaded.data["edge"] == "0.1"


async def test_patches_cannot_set_reserved_keys_or_renew_offer_freshness(store):
    opp = opportunity()
    await offer(store, opp)
    offered = await store.offered_at(opp.id)
    forged = {
        key: "forged"
        for key in (REVISION_KEY, APPROVABLE_KEY, ORDER_TERMS_KEY, BROKER_KEY, EXIT_KEY)
    }
    assert await store.update_data(opp.id, forged)
    await assert_current(store, opp)
    assert await store.mark_approvable(opp.id, revision=opp.data[REVISION_KEY])
    assert await store.offered_at(opp.id) == offered


async def test_old_revision_cannot_claim_expire_or_release_a_newer_revision(store):
    first, replacement = opportunity(), opportunity("500")
    await offer(store, first)
    await offer(store, replacement)
    for expected, to in [
        (OpportunityStatus.PENDING, OpportunityStatus.APPROVED),
        (OpportunityStatus.PENDING, OpportunityStatus.EXPIRED),
        (OpportunityStatus.APPROVED, OpportunityStatus.PENDING),
    ]:
        assert not await store.transition(
            first.id, expected, to, revision=first.data[REVISION_KEY]
        )
    assert (await store.get(first.id))["status"] == "pending"
    await assert_current(store, replacement)


async def test_claim_retries_metadata_conflicts_and_still_has_one_winner(store, writer):
    opp = opportunity()
    await offer(store, opp)
    after_read(store, lambda: writer.update_data(opp.id, {"new_note": "keep"}))
    results = await asyncio.gather(
        *(
            s.transition(
                opp.id,
                OpportunityStatus.PENDING,
                OpportunityStatus.APPROVED,
                revision=opp.data[REVISION_KEY],
            )
            for s in (store, writer)
        )
    )
    assert results.count(True) == 1
    assert (await assert_current(store, opp)).data["new_note"] == "keep"


async def test_metadata_on_missing_id_does_not_create_a_row(store):
    assert not await store.update_data("missing", {"note": "x"})
    assert not await store.mark_approvable("missing", revision="missing")
    assert await store.get("missing") is None


@pytest.mark.parametrize("raw", [None, "null"])
async def test_metadata_patch_preserves_nullable_legacy_rows_without_making_an_offer(
    store, raw
):
    opp = opportunity()
    await store.save(opp)
    await store._db.execute("UPDATE opportunities SET data=? WHERE id=?", (raw, opp.id))
    await store._db.commit()
    assert await store.update_data(opp.id, {"note": "keep"})
    assert not await store.is_approvable(opp.id)
    assert (await store.get(opp.id))["status"] == "pending"
    assert (await store.load(opp.id)).data == {"note": "keep"}
