"""Unit tests for storage.postgres.PostgresDB.

These tests exercise the adapter logic only — no real PostgreSQL connection is
needed.  The asyncpg pool is replaced with a lightweight AsyncMock so that we
can verify argument passing without an external database.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from storage.postgres import PostgresDB


# ---------------------------------------------------------------------------
# _convert_placeholders — pure function, no I/O
# ---------------------------------------------------------------------------


class TestConvertPlaceholders:
    def test_no_placeholders_unchanged(self):
        sql = "SELECT * FROM opportunities WHERE status = 'pending'"
        assert PostgresDB._convert_placeholders(sql) == sql

    def test_single_placeholder(self):
        sql = "SELECT * FROM opportunities WHERE id = ?"
        result = PostgresDB._convert_placeholders(sql)
        assert result == "SELECT * FROM opportunities WHERE id = $1"

    def test_two_placeholders(self):
        sql = "SELECT * FROM trades WHERE agent_name = ? AND status = ?"
        result = PostgresDB._convert_placeholders(sql)
        assert result == "SELECT * FROM trades WHERE agent_name = $1 AND status = $2"

    def test_three_placeholders(self):
        sql = (
            "INSERT INTO risk_events (event_type, details, created_at) VALUES (?, ?, ?)"
        )
        result = PostgresDB._convert_placeholders(sql)
        assert result == (
            "INSERT INTO risk_events (event_type, details, created_at) VALUES ($1, $2, $3)"
        )

    def test_placeholder_at_start(self):
        sql = "? = 1"
        result = PostgresDB._convert_placeholders(sql)
        assert result == "$1 = 1"

    def test_placeholder_at_end(self):
        sql = "SELECT 1 WHERE id = ?"
        result = PostgresDB._convert_placeholders(sql)
        assert result == "SELECT 1 WHERE id = $1"

    def test_consecutive_placeholders(self):
        sql = "VALUES (?, ?, ?, ?)"
        result = PostgresDB._convert_placeholders(sql)
        assert result == "VALUES ($1, $2, $3, $4)"

    def test_empty_string(self):
        assert PostgresDB._convert_placeholders("") == ""

    def test_known_limitation_placeholder_in_literal(self):
        """? inside a SQL string literal is mis-converted — document as known limitation."""
        sql = "SELECT * FROM t WHERE col LIKE '%?%' AND id = ?"
        result = PostgresDB._convert_placeholders(sql)
        # Both '?' are converted — the one inside the literal becomes $1,
        # the real bind parameter becomes $2.  This is the documented limitation.
        assert "$1" in result
        assert "$2" in result


# ---------------------------------------------------------------------------
# execute / fetchone / fetchall / executemany — verify pool interaction
# ---------------------------------------------------------------------------


def _make_db():
    """Return a PostgresDB wrapping a mock asyncpg pool."""
    pool = MagicMock()

    # asyncpg pool is used as an async context manager: `async with pool.acquire() as conn`
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.executemany = AsyncMock(return_value=None)

    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_ctx)

    return PostgresDB(pool), pool, conn


@pytest.mark.asyncio
async def test_execute_converts_placeholders_and_calls_pool():
    db, pool, conn = _make_db()
    await db.execute("DELETE FROM trades WHERE id = ?", [42])
    conn.execute.assert_awaited_once_with("DELETE FROM trades WHERE id = $1", 42)


@pytest.mark.asyncio
async def test_execute_no_params():
    db, pool, conn = _make_db()
    await db.execute("DELETE FROM trades")
    conn.execute.assert_awaited_once_with("DELETE FROM trades")


@pytest.mark.asyncio
async def test_fetchone_returns_none_when_no_row():
    db, pool, conn = _make_db()
    conn.fetchrow = AsyncMock(return_value=None)
    result = await db.fetchone("SELECT * FROM opportunities WHERE id = ?", ["abc"])
    assert result is None


@pytest.mark.asyncio
async def test_fetchone_returns_dict():
    db, pool, conn = _make_db()
    fake_row = {"id": "opp-1", "symbol": "AAPL", "status": "pending"}
    conn.fetchrow = AsyncMock(return_value=fake_row)
    result = await db.fetchone("SELECT * FROM opportunities WHERE id = ?", ["opp-1"])
    assert result == fake_row
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_fetchall_returns_list_of_dicts():
    db, pool, conn = _make_db()
    fake_rows = [
        {"id": 1, "event_type": "fill"},
        {"id": 2, "event_type": "reject"},
    ]
    conn.fetch = AsyncMock(return_value=fake_rows)
    result = await db.fetchall("SELECT * FROM risk_events WHERE id > ?", [0])
    assert result == fake_rows
    assert all(isinstance(r, dict) for r in result)


@pytest.mark.asyncio
async def test_fetchall_empty():
    db, pool, conn = _make_db()
    conn.fetch = AsyncMock(return_value=[])
    result = await db.fetchall("SELECT * FROM risk_events")
    assert result == []


@pytest.mark.asyncio
async def test_executemany_converts_placeholders():
    db, pool, conn = _make_db()
    params_list = [("agent_a", "AAPL"), ("agent_b", "TSLA")]
    await db.executemany(
        "INSERT INTO opportunities (agent_name, symbol) VALUES (?, ?)",
        params_list,
    )
    conn.executemany.assert_awaited_once_with(
        "INSERT INTO opportunities (agent_name, symbol) VALUES ($1, $2)",
        params_list,
    )


# ---------------------------------------------------------------------------
# execute as async context manager (``async with db.execute(...) as cursor:``)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_as_context_manager_returns_cursor():
    """async with db.execute(...) as cursor: should return a cursor-like object."""
    db, pool, conn = _make_db()
    fake_rows = [{"id": 1, "symbol": "AAPL"}, {"id": 2, "symbol": "TSLA"}]
    conn.fetch = AsyncMock(return_value=fake_rows)

    async with db.execute(
        "SELECT * FROM external_balances WHERE broker = ?", ["fidelity"]
    ) as cursor:
        rows = await cursor.fetchall()

    assert rows == fake_rows
    conn.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_as_context_manager_fetchone():
    """Cursor returned by async with db.execute() supports fetchone()."""
    db, pool, conn = _make_db()
    fake_rows = [{"id": 1, "net_liquidation": "100000.00"}]
    conn.fetch = AsyncMock(return_value=fake_rows)

    async with db.execute(
        "SELECT * FROM paper_accounts WHERE account_id = ?", ["PAPER"]
    ) as cursor:
        row = await cursor.fetchone()

    assert row == {"id": 1, "net_liquidation": "100000.00"}


@pytest.mark.asyncio
async def test_execute_as_context_manager_empty_result():
    """Cursor fetchone() returns None when no rows are found."""
    db, pool, conn = _make_db()
    conn.fetch = AsyncMock(return_value=[])

    async with db.execute(
        "SELECT * FROM paper_accounts WHERE account_id = ?", ["MISSING"]
    ) as cursor:
        row = await cursor.fetchone()

    assert row is None


@pytest.mark.asyncio
async def test_execute_supports_both_await_and_context_manager():
    """db.execute() should work with both `await` and `async with`."""
    db, pool, conn = _make_db()

    # Pattern 1: plain await (for INSERT/UPDATE/DELETE)
    await db.execute("DELETE FROM trades WHERE id = ?", [42])
    conn.execute.assert_awaited_once()

    # Reset mock
    conn.execute.reset_mock()
    conn.fetch = AsyncMock(return_value=[{"count": 5}])

    # Pattern 2: async with (for SELECT with cursor)
    async with db.execute("SELECT count(*) as count FROM trades") as cursor:
        row = await cursor.fetchone()
    assert row == {"count": 5}


# ---------------------------------------------------------------------------
# await db.execute(SELECT ...) — returns cursor (aiosqlite parity)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_await_select_returns_cursor():
    """await db.execute('SELECT ...') must return a cursor, not None."""
    db, pool, conn = _make_db()
    fake_rows = [{"agent_name": "momentum", "status": "normal"}]
    conn.fetch = AsyncMock(return_value=fake_rows)

    cursor = await db.execute(
        "SELECT * FROM strategy_health WHERE agent_name = ?", ["momentum"]
    )
    row = await cursor.fetchone()
    assert row == {"agent_name": "momentum", "status": "normal"}


@pytest.mark.asyncio
async def test_await_select_empty_returns_cursor_with_none():
    """await db.execute('SELECT ...') returns cursor whose fetchone() yields None when empty."""
    db, pool, conn = _make_db()
    conn.fetch = AsyncMock(return_value=[])

    cursor = await db.execute(
        "SELECT * FROM strategy_health WHERE agent_name = ?", ["missing"]
    )
    row = await cursor.fetchone()
    assert row is None


@pytest.mark.asyncio
async def test_await_insert_returns_empty_cursor():
    """await db.execute('INSERT ...') returns an empty cursor (no rows)."""
    db, pool, conn = _make_db()
    cursor = await db.execute("INSERT INTO trades (id) VALUES (?)", [1])
    row = await cursor.fetchone()
    assert row is None


# ---------------------------------------------------------------------------
# _convert_insert_or_replace — composite PK handling
# ---------------------------------------------------------------------------


class TestConvertInsertOrReplaceCompositePK:
    def test_composite_pk_strategy_confidence_calibration(self):
        sql = "INSERT OR REPLACE INTO strategy_confidence_calibration (agent_name, confidence_bucket, window_label, trade_count) VALUES (?, ?, ?, ?)"
        result = PostgresDB._convert_insert_or_replace(sql)
        assert "ON CONFLICT (agent_name, confidence_bucket, window_label)" in result
        assert "trade_count=EXCLUDED.trade_count" in result
        assert "INSERT INTO strategy_confidence_calibration" in result
        assert "INSERT OR REPLACE" not in result

    def test_composite_pk_consensus_votes(self):
        sql = "INSERT OR REPLACE INTO consensus_votes (symbol, side, agent_name, opportunity_id, voted_at) VALUES (?, ?, ?, ?, ?)"
        result = PostgresDB._convert_insert_or_replace(sql)
        assert "ON CONFLICT (symbol, side, agent_name)" in result
        assert "opportunity_id=EXCLUDED.opportunity_id" in result
        assert "voted_at=EXCLUDED.voted_at" in result

    def test_single_pk_unchanged(self):
        sql = "INSERT OR REPLACE INTO agent_overrides (agent_name, trust_level) VALUES (?, ?)"
        result = PostgresDB._convert_insert_or_replace(sql)
        assert "ON CONFLICT (agent_name)" in result
        assert "trust_level=EXCLUDED.trust_level" in result


# ---------------------------------------------------------------------------
# Date and time arguments — the driver's refusals are simulated
# ---------------------------------------------------------------------------


class DataError(Exception):
    """Stands in for asyncpg.DataError, which is matched by name."""


class _Typed:
    """A connection that refuses arguments the way asyncpg does, per column type."""

    def __init__(self, *types):
        self.types, self.calls = types, []

    async def fetch(self, sql, *args):
        from datetime import date, datetime

        self.calls.append(args)
        for position, (kind, value) in enumerate(zip(self.types, args), start=1):
            head = f"invalid input for query argument ${position}: {value!r}"
            if value is None:
                continue
            if kind == "text":
                if not isinstance(value, str):
                    raise DataError(f"{head} (expected str, got {type(value).__name__})")
                continue
            if isinstance(value, str):
                detail = (
                    "'str' object has no attribute 'toordinal'"
                    if kind == "date"
                    else "expected a datetime.date or datetime.datetime instance, got 'str'"
                )
                raise DataError(f"{head} ({detail})")
            if kind == "timestamp" and isinstance(value, datetime) and value.tzinfo:
                raise DataError(
                    f"{head} (can't subtract offset-naive and offset-aware datetimes)"
                )
            assert isinstance(value, date)
        return []


class TestTemporalArguments:
    async def run(self, connection, params, learned=None):
        from storage.postgres import _run

        learned = {} if learned is None else learned
        await _run(connection.fetch, "SQL", params, learned)
        return connection.calls[-1], learned

    async def test_text_becomes_what_each_column_takes(self):
        from datetime import date, datetime, timedelta, timezone

        text = "2026-11-12T21:30:00+09:00"
        instant = datetime(2026, 11, 12, 21, 30, tzinfo=timezone(timedelta(hours=9)))
        bound, learned = await self.run(
            _Typed("date", "timestamp", "timestamptz", "text"),
            ("2026-11-12", text, text, text),
        )
        assert bound == (date(2026, 11, 12), datetime(2026, 11, 12, 12, 30), instant, text)
        assert learned == {"SQL": {0: "date", 1: "naive", 2: "aware"}}

    async def test_a_datetime_becomes_text_for_a_text_column(self):
        from datetime import date, datetime, timezone

        stamp = datetime(2026, 11, 12, 12, 30, tzinfo=timezone.utc)
        bound, learned = await self.run(
            _Typed("text", "text", "text"), (stamp, date(2026, 11, 12), "kept")
        )
        assert bound == ("2026-11-12T12:30:00+00:00", "2026-11-12", "kept")
        assert learned == {"SQL": {0: "text", 1: "text"}}
        # Text already bound there later is left as it is.
        bound, _ = await self.run(_Typed("text", "text", "text"), ("a", "b", "c"), learned)
        assert bound == ("a", "b", "c")

    async def test_a_learned_statement_binds_right_first_time(self):
        connection = _Typed("timestamp")
        _, learned = await self.run(connection, ("2026-11-12T12:30:00+00:00",))
        attempts = len(connection.calls)
        await self.run(connection, ("2026-11-13T12:30:00+00:00",), learned)
        assert attempts == 3 and len(connection.calls) == attempts + 1

    async def test_nothing_is_learned_when_the_statement_then_fails(self):
        class ThenFails(_Typed):
            async def fetch(self, sql, *args):
                await super().fetch(sql, *args)
                raise RuntimeError("unique violation")

        learned = {}
        with pytest.raises(RuntimeError):
            await self.run(ThenFails("timestamp"), ("2026-11-12T12:30:00",), learned)
        assert learned == {}

    async def test_text_that_is_not_a_date_is_raised_unchanged(self):
        connection = _Typed("timestamp")
        with pytest.raises(DataError):
            await self.run(connection, ("soon",))
        assert len(connection.calls) == 1

    async def test_a_refusal_of_a_non_temporal_argument_is_raised(self):
        class RefusesInt:
            calls = 0

            async def fetch(self, sql, *args):
                type(self).calls += 1
                raise DataError(
                    "invalid input for query argument $1: '2026-11-12' (an integer is required)"
                )

        with pytest.raises(DataError):
            await self.run(RefusesInt(), ("2026-11-12",))
        assert RefusesInt.calls == 1

    async def test_another_error_class_is_never_retried(self):
        class Other:
            calls = 0

            async def fetch(self, sql, *args):
                type(self).calls += 1
                raise ValueError(
                    "invalid input for query argument $1: 'x' (expected a datetime)"
                )

        with pytest.raises(ValueError):
            await self.run(Other(), ("2026-11-12T00:00:00",))
        assert Other.calls == 1

    async def test_simultaneous_first_calls_each_recover(self):
        import asyncio

        connection = _Typed("timestamp")
        learned = {}
        await asyncio.gather(
            *(self.run(connection, ("2026-11-12T12:30:00+00:00",), learned) for _ in range(3))
        )
        assert learned == {"SQL": {0: "naive"}}


class TestRow:
    def test_a_row_reads_by_name_and_by_position(self):
        from storage.postgres import _Row

        row = _Row({"id": 7, "name": "x"})
        assert (row["id"], row[0], row[1], row[-1]) == (7, 7, "x", "x")
        assert isinstance(row, dict) and dict(row) == {"id": 7, "name": "x"}
        assert row.get("name") == "x"
        with pytest.raises(IndexError):
            row[2]
        with pytest.raises(KeyError):
            row["missing"]


class TestEngineDdl:
    def test_boolean_columns_do_not_default_to_an_integer(self):
        """PostgreSQL rejects it, and one rejected statement loses every table."""
        import re

        from storage.db import _INIT_DDL

        assert re.findall(r"BOOLEAN[^,\n]*DEFAULT\s+[01]\b", _INIT_DDL, re.I) == []
