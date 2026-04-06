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
