"""cursor.rowcount and cursor.lastrowid through the PostgreSQL facade.

Stores written for SQLite read both. PostgreSQL reports affected rows in a
status string and gives a generated id back only when the statement asks.
"""

import os
from uuid import uuid4

import asyncpg
import pytest

from datetime import datetime, timedelta, timezone

from feeds.pnl_attribution import FeedArbPnLAttribution
from learning.reflection import PredictionTracker
from learning.tournament import TournamentRunner
from storage.db import init_db_postgres
from storage.postgres import PostgresDB

pytestmark = pytest.mark.integration


@pytest.fixture
async def db():
    dsn = os.environ.get("AMU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail("AMU_TEST_POSTGRES_DSN must identify a disposable test database")
    schema = "cursor_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=4,
        statement_cache_size=0,
        server_settings={"search_path": schema},
    )
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                "CREATE TABLE items (id SERIAL PRIMARY KEY, name TEXT UNIQUE, n INT DEFAULT 0);"
                "CREATE TABLE modern (id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, name TEXT);"
                "CREATE TABLE keyed (name TEXT PRIMARY KEY, n INT)"
            )
        yield PostgresDB(pool)
    finally:
        await pool.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


async def test_an_insert_reports_the_id_it_generated(db):
    first = await db.execute("INSERT INTO items (name) VALUES (?)", ("a",))
    second = await db.execute("INSERT INTO items (name) VALUES (?);", ("b",))
    assert (first.lastrowid, second.lastrowid) == (1, 2)
    assert (first.rowcount, second.rowcount) == (1, 1)
    assert await first.fetchone() is None  # the caller did not ask for rows
    identity = await db.execute("INSERT INTO modern (name) VALUES (?)", ("a",))
    assert identity.lastrowid == 1


async def test_an_insert_that_writes_nothing_reports_no_id(db):
    await db.execute("INSERT INTO items (name) VALUES (?)", ("a",))
    again = await db.execute("INSERT OR IGNORE INTO items (name) VALUES (?)", ("a",))
    assert again.lastrowid is None
    assert again.rowcount == 0


async def test_a_table_with_no_generated_id_reports_none(db):
    cursor = await db.execute("INSERT INTO keyed (name, n) VALUES (?, ?)", ("a", 1))
    assert cursor.lastrowid is None
    assert cursor.rowcount == 1
    replaced = await db.execute(
        "INSERT OR REPLACE INTO keyed (name, n) VALUES (?, ?)", ("a", 2)
    )
    assert replaced.rowcount == 1
    assert (await db.fetchone("SELECT n FROM keyed"))["n"] == 2


async def test_update_and_delete_report_the_rows_they_changed(db):
    for name in "abc":
        await db.execute("INSERT INTO items (name) VALUES (?)", (name,))
    updated = await db.execute("UPDATE items SET n = 1 WHERE name <> ?", ("c",))
    none = await db.execute("UPDATE items SET n = 2 WHERE name = ?", ("zzz",))
    assert (updated.rowcount, none.rowcount) == (2, 0)
    async with db.execute("DELETE FROM items WHERE n = ?", (1,)) as deleted:
        assert deleted.rowcount == 2
    selected = await db.execute("SELECT * FROM items")
    assert selected.rowcount == -1 and len(await selected.fetchall()) == 1


async def test_keywords_inside_text_and_comments_are_not_read_as_sql(db):
    text = await db.execute("INSERT INTO items (name) VALUES ('returning to base')")
    commented = await db.execute(
        "-- add one\nINSERT INTO items (name) VALUES (?) -- the name", ("b",)
    )
    updated = await db.execute("UPDATE items SET name = 'x RETURNING y' WHERE id = 1")
    assert (text.lastrowid, commented.lastrowid) == (1, 2)
    assert (text.rowcount, commented.rowcount, updated.rowcount) == (1, 1, 1)


@pytest.mark.parametrize(
    "sql, expected",
    [
        ("-- every item\nSELECT name FROM items", 1),
        ("(SELECT 1) UNION (SELECT 2)", 2),
        ("EXPLAIN SELECT 1", 1),
    ],
)
async def test_an_opened_cursor_gets_rows_from_any_statement(db, sql, expected):
    await db.execute("INSERT INTO items (name) VALUES (?)", ("a",))
    async with db.execute(sql) as cursor:
        assert len(await cursor.fetchall()) == expected


async def test_a_renamed_id_column_is_looked_up_again(db):
    await db.execute("INSERT INTO items (name) VALUES (?)", ("a",))
    await db.execute("ALTER TABLE items RENAME COLUMN id TO item_id")
    with pytest.raises(asyncpg.UndefinedColumnError):
        await db.execute("INSERT INTO items (name) VALUES (?)", ("b",))
    cursor = await db.execute("INSERT INTO items (name) VALUES (?)", ("c",))
    assert cursor.lastrowid is not None


async def test_a_statement_that_asks_for_rows_still_gets_them(db):
    cursor = await db.execute("INSERT INTO items (name) VALUES (?) RETURNING id, name", ("a",))
    assert dict(await cursor.fetchone()) == {"id": 1, "name": "a"}
    async with db.execute("UPDATE items SET n = 5 RETURNING n") as updated:
        assert [r["n"] for r in await updated.fetchall()] == [5]


async def test_the_id_is_reported_inside_a_transaction_too(db):
    async with db.transaction() as tx:
        first = await tx.execute("INSERT INTO items (name) VALUES (?)", ("a",))
        second = await tx.execute("INSERT INTO items (name) VALUES (?)", ("b",))
    assert (first.lastrowid, second.lastrowid) == (1, 2)
    third = await db.execute("INSERT INTO items (name) VALUES (?)", ("c",))
    assert third.lastrowid == 3


async def test_a_table_created_after_a_failed_insert_is_looked_up_again(db):
    with pytest.raises(asyncpg.UndefinedTableError):
        await db.execute("INSERT INTO later (name) VALUES (?)", ("a",))
    await db.executescript("CREATE TABLE later (id SERIAL PRIMARY KEY, name TEXT)")
    assert (await db.execute("INSERT INTO later (name) VALUES (?)", ("a",))).lastrowid == 1


async def test_a_tournament_round_and_its_variants_share_the_generated_id(db):
    """learning/tournament.py reads cursor.lastrowid to link variants to a round."""
    await init_db_postgres(db)
    runner = TournamentRunner(db)
    first = await runner.start_round(
        agent_name="agent", champion_params={"p": 1}, challenger_params_list=[{"p": 2}, {"p": 3}]
    )
    second = await runner.start_round(
        agent_name="agent", champion_params={"p": 1}, challenger_params_list=[]
    )
    assert isinstance(first, int) and second == first + 1
    variants = await db.fetchall(
        "SELECT variant_label FROM tournament_variants WHERE round_id = ? ORDER BY id",
        (first,),
    )
    assert [v["variant_label"] for v in variants] == ["champion", "challenger_0", "challenger_1"]
    assert (await runner.get_round(first))["agent_name"] == "agent"


async def test_archiving_lessons_reports_how_many_were_archived(db):
    """learning/reflection.py returns cursor.rowcount from an UPDATE."""
    await init_db_postgres(db)
    tracker = PredictionTracker(db)
    for i in range(3):
        await tracker.save_lesson("agent", f"opp-{i}", "timing", "lesson", ["AAPL"])
    await tracker.save_lesson("other", "opp-9", "timing", "lesson", ["AAPL"])
    assert await tracker.archive_lessons("agent") == 3
    assert await tracker.archive_lessons("agent") == 0


async def test_feed_signal_outcomes_count_only_the_rows_they_set(db):
    """feeds/pnl_attribution.py counts filled and missed signals by rowcount."""
    await init_db_postgres(db)
    now = datetime.now(timezone.utc)
    for signal_id, expires in (("live", 60), ("old-1", -60), ("old-2", -90)):
        await db.execute(
            "INSERT INTO feed_arb_signals (signal_id, ts, pair_kalshi_ticker,"
            " pair_kalshi_side, pair_poly_token_id, pair_poly_side, edge_cents,"
            " max_size_at_edge_usd, expires_at, raw_signal)"
            " VALUES (?, ?, 'K', 'yes', 'P', 'no', 1, 1, ?, '{}')",
            (signal_id, now, now + timedelta(seconds=expires)),
        )
    attribution = FeedArbPnLAttribution(db)
    filled = await attribution._mark_as_filled({"live", "unknown"}, now)
    again = await attribution._mark_as_filled({"live"}, now)
    missed = await attribution._mark_expired_as_missed(now)
    assert (filled, again, missed) == (1, 0, 2)
