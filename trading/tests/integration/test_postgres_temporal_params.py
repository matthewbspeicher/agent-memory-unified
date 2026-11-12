"""Date and time arguments through the PostgreSQL facade, on a disposable schema.

Stores bind ISO text, as SQLite takes it. The facade must turn that into what
DATE, TIMESTAMP and TIMESTAMPTZ columns take, without changing the instant, in
a session whose time zone is not UTC.
"""

import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from storage.consensus import ConsensusStore
from storage.performance import PerformanceSnapshot, PerformanceStore
from storage.postgres import PostgresDB
from storage.spreads import SpreadObservation, SpreadStore
from storage.strategy_health import StrategyHealthStore

pytestmark = pytest.mark.integration

_SCRIPT = (Path(__file__).parents[3] / "scripts" / "init-trading-tables.sql").read_text()
TOKYO = timezone(timedelta(hours=9))
INSTANT = datetime(2026, 11, 12, 21, 30, tzinfo=TOKYO)  # 12:30 UTC
UTC_WALL = datetime(2026, 11, 12, 12, 30)
INSERT = "INSERT INTO moments (id, d, ts, tstz, note) VALUES (?, ?, ?, ?, ?)"


def script_table(name: str) -> str:
    return re.search(
        rf"CREATE TABLE IF NOT EXISTS {name} \(.*?\);", _SCRIPT, re.S
    ).group(0)


@pytest.fixture
async def db():
    dsn = os.environ.get("AMU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail("AMU_TEST_POSTGRES_DSN must identify a disposable test database")
    schema = "temporal_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=4,
        statement_cache_size=0,  # as the engine's pool is configured
        server_settings={"search_path": schema, "timezone": "Asia/Tokyo"},
    )
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                "CREATE TABLE moments (id TEXT PRIMARY KEY, d DATE, ts TIMESTAMP,"
                " tstz TIMESTAMPTZ, note TEXT)"
            )
            for table in (
                "consensus_votes",
                "arb_spread_observations",
                "strategy_health",
                "performance_snapshots",
            ):
                await connection.execute(script_table(table))
        yield PostgresDB(pool)
    finally:
        await pool.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


async def stored(db, id):
    return await db.fetchone("SELECT * FROM moments WHERE id = ?", (id,))


async def test_iso_text_is_stored_as_the_same_instant(db):
    text = INSTANT.isoformat()
    await db.execute(INSERT, ("a", "2026-11-12", text, text, text))
    row = await stored(db, "a")
    assert row["d"] == date(2026, 11, 12)
    assert row["ts"] == UTC_WALL  # the column has no time zone; it holds UTC
    assert row["tstz"] == INSTANT
    assert row["note"] == text  # a TEXT column keeps ISO text as text


async def test_text_without_an_offset_is_read_as_utc(db):
    text = UTC_WALL.isoformat()
    await db.execute(INSERT, ("a", text, text, text, None))
    row = await stored(db, "a")
    assert row["d"] == date(2026, 11, 12)
    assert row["ts"] == UTC_WALL
    assert row["tstz"] == UTC_WALL.replace(tzinfo=timezone.utc)


async def test_aware_datetime_is_stored_in_a_plain_timestamp_as_utc(db):
    await db.execute(INSERT, ("a", INSTANT, INSTANT, INSTANT, None))
    row = await stored(db, "a")
    assert row["ts"] == UTC_WALL
    assert row["tstz"] == INSTANT


async def test_values_the_driver_already_takes_are_untouched(db):
    await db.execute(INSERT, ("a", date(2026, 11, 12), UTC_WALL, INSTANT, None))
    await db.execute(INSERT, ("b", None, None, None, None))
    row = await stored(db, "a")
    assert (row["d"], row["ts"], row["tstz"]) == (date(2026, 11, 12), UTC_WALL, INSTANT)
    assert (await stored(db, "b"))["ts"] is None
    assert db._learned == {}


async def test_a_statement_is_corrected_once_then_bound_right_first_time(db):
    text = INSTANT.isoformat()
    await db.execute(INSERT, ("a", "2026-11-12", text, text, None))
    learned = dict(db._learned)
    assert len(learned) == 1
    await db.execute(INSERT, ("b", "2026-11-13", text, text, None))
    assert db._learned == learned
    assert (await stored(db, "b"))["d"] == date(2026, 11, 13)


async def test_text_filters_work_on_every_read_path(db):
    await db.execute(INSERT, ("old", None, "2026-11-01T00:00:00+00:00", None, None))
    await db.execute(INSERT, ("new", None, "2026-11-12T12:30:00+00:00", None, None))
    query = "SELECT id FROM moments WHERE ts >= ? ORDER BY id"
    cutoff = ("2026-11-10T00:00:00+00:00",)
    assert [r["id"] for r in await db.fetchall(query, cutoff)] == ["new"]
    assert (await db.fetchone(query, cutoff))["id"] == "new"
    async with db.execute(query, cutoff) as cursor:
        assert [r["id"] for r in await cursor.fetchall()] == ["new"]
    cursor = await db.execute(query, cutoff)
    assert (await cursor.fetchone())["id"] == "new"


async def test_a_refused_attempt_does_not_break_the_transaction(db):
    text = INSTANT.isoformat()
    async with db.transaction() as tx:
        await tx.execute(INSERT, ("first", None, None, None, "before"))
        await tx.execute(INSERT, ("second", "2026-11-12", text, text, None))
    assert (await stored(db, "first"))["note"] == "before"
    assert (await stored(db, "second"))["ts"] == UTC_WALL
    # The transaction's facade shares what it learned with the root one.
    assert len(db._learned) == 1


async def test_text_that_is_not_a_date_is_still_refused(db):
    with pytest.raises(asyncpg.DataError):
        await db.execute(INSERT, ("a", "1y", None, None, None))
    with pytest.raises(asyncpg.DataError):
        await db.execute(INSERT, ("a", None, "soon", None, None))
    assert await stored(db, "a") is None
    assert db._learned == {}


async def test_stores_that_bind_text_now_write(db):
    await ConsensusStore(db).add_vote("AAPL", "buy", "agent", "opp-1", INSTANT)
    await StrategyHealthStore(db).upsert_status(
        "agent", "healthy", cooldown_until=INSTANT.isoformat()
    )
    observation = await SpreadStore(db).record(
        SpreadObservation("KX", "POLY", 0.9, 50, 58, 8)
    )
    assert observation is not None
    # Stores written for SQLite read rows by position; that must work here too.
    assert (await SpreadStore(db).get_observation(observation))["gap_cents"] == 8
    vote = await db.fetchone("SELECT voted_at FROM consensus_votes")
    assert vote["voted_at"] == UTC_WALL
    health = await db.fetchone("SELECT cooldown_until FROM strategy_health")
    assert health["cooldown_until"] == UTC_WALL


async def test_a_snapshot_written_as_text_is_read_back_as_the_same_instant(db):
    """The reader parsed this column as text; PostgreSQL returns a datetime."""
    store = PerformanceStore(db)
    await store.save(
        PerformanceSnapshot(
            agent_name="agent",
            timestamp=INSTANT,
            opportunities_generated=3,
            opportunities_executed=1,
            win_rate=0.5,
        )
    )
    latest = await store.get_latest("agent")
    assert latest.timestamp == INSTANT
    assert latest.timestamp.tzinfo is not None
