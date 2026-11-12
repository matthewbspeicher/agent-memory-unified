from __future__ import annotations

import re
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

# Stores are written for SQLite, where dates and times are ISO text. asyncpg
# takes only date/datetime objects for DATE, TIMESTAMP and TIMESTAMPTZ
# parameters, only naive datetimes for TIMESTAMP, and only text for TEXT (the
# type the engine's own DDL gives time columns). It refuses anything else
# while encoding the arguments, before the statement is run, and names the
# argument. It likewise takes only a bool for BOOLEAN, where stores bind the 0
# and 1 SQLite uses. _run converts that argument and tries again, then remembers the
# conversion for the statement so later calls bind correctly first time.
_REFUSED_ARGUMENT = re.compile(r"invalid input for query argument \$(\d+):")
_WANTS_DATETIME = "expected a datetime"
_WANTS_DATE = "has no attribute 'toordinal'"
_WANTS_NAIVE = "offset-naive and offset-aware"
_WANTS_TEXT = "expected str, got "
_WANTS_BOOL = "a boolean is required"
_AWARE, _NAIVE, _DATE, _TEXT, _BOOL = "aware", "naive", "date", "text", "bool"
_MAX_LEARNED_STATEMENTS = 4096

# SQLSTATE for "no unique or exclusion constraint matching the ON CONFLICT
# specification": this database's key for the table is not the registered one.
_NO_MATCHING_KEY = "42P10"
# Translated upsert -> the same upsert keyed on its first column, which is what
# the facade always used before a key was registered for the table. A database
# created from an older definition may still have that key.
_FIRST_COLUMN_UPSERTS: dict[str, str] = {}


def _as_aware(value):
    """ISO text as a UTC-aware datetime, or None if it is not ISO text."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _convert(value, mode):
    """Apply a remembered conversion; values it does not fit are left alone."""
    if mode is None or value is None:
        return value
    if mode == _BOOL:
        # SQLite has no boolean type, so stores bind 0 and 1.
        return bool(value) if type(value) is int and value in (0, 1) else value
    if mode == _TEXT:
        # A TEXT column holding times: ISO text, as stores write it themselves.
        return value.isoformat() if isinstance(value, (datetime, date)) else value
    if isinstance(value, str):
        parsed = _as_aware(value.strip())
        if parsed is None:
            return value
        # A DATE column takes the calendar date as written, not shifted to UTC.
        value = parsed.date() if mode == _DATE else parsed
    if mode == _NAIVE and isinstance(value, datetime) and value.tzinfo is not None:
        # A TIMESTAMP column has no time zone; it holds UTC.
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _correction(error, args):
    """(index, converted value, mode) for a temporal argument the driver refused."""
    if type(error).__name__ != "DataError":
        return None
    message = str(error)
    match = _REFUSED_ARGUMENT.search(message)
    if match is None or not 0 < int(match.group(1)) <= len(args):
        return None
    index = int(match.group(1)) - 1
    value = args[index]
    if isinstance(value, str):
        mode = (
            _AWARE
            if _WANTS_DATETIME in message
            else _DATE
            if _WANTS_DATE in message
            else None
        )
        converted = _convert(value, mode)
        return None if converted is value else (index, converted, mode)
    if type(value) is int and value in (0, 1) and _WANTS_BOOL in message:
        return index, bool(value), _BOOL
    if isinstance(value, (datetime, date)) and _WANTS_TEXT in message:
        return index, _convert(value, _TEXT), _TEXT
    if (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and _WANTS_NAIVE in message
    ):
        return index, _convert(value, _NAIVE), _NAIVE
    return None


async def _run(call, sql, params, learned):
    """Call an asyncpg method, converting date and time arguments it refuses."""
    args = list(params or [])
    sql = learned.get((_NO_MATCHING_KEY, sql), sql)
    plan = learned.get(sql)
    if plan:
        args = [_convert(arg, plan.get(i)) for i, arg in enumerate(args)]
    corrections = {}
    while True:
        try:
            result = await call(sql, *args)
            break
        except Exception as error:
            older = _FIRST_COLUMN_UPSERTS.get(sql)
            if older and getattr(error, "sqlstate", None) == _NO_MATCHING_KEY:
                # The server rejected the statement, so nothing was written. It
                # also aborted any open transaction, where this retry will fail.
                logger.warning(
                    "This database's unique key differs from the engine's"
                    " definition; replacing on the first column instead: %s",
                    " ".join(sql.split())[:90],
                )
                learned[(_NO_MATCHING_KEY, sql)] = older
                sql = older
                continue
            step = _correction(error, args)
            if step is None:
                raise
            index, args[index], corrections[index] = step
    if corrections:
        if len(learned) >= _MAX_LEARNED_STATEMENTS:
            learned.clear()
        learned[sql] = {**learned.get(sql, {}), **corrections}
    return result


class _Row(dict):
    """A result row readable by column name or, like an aiosqlite row, by position."""

    def __init__(self, record) -> None:
        super().__init__(record)
        # Kept apart from the mapping: two columns may share a name.
        self._positional = tuple(record.values())

    def __getitem__(self, key):
        if isinstance(key, int) and not isinstance(key, bool):
            return self._positional[key]
        return super().__getitem__(key)


class _PostgresCursor:
    """Mimics an aiosqlite cursor so ``async with db.execute(...) as cur:``
    works identically for both backends.

    Holds the rows returned by a SELECT statement and exposes ``fetchone``
    and ``fetchall`` matching the aiosqlite cursor interface.
    """

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self._index = 0

    async def fetchone(self) -> dict | None:
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return row
        return None

    async def fetchall(self) -> list[dict]:
        remaining = self._rows[self._index :]
        self._index = len(self._rows)
        return remaining


class _PostgresContextManager:
    """Returned by :meth:`PostgresDB.execute`.

    Supports **both** usage patterns used across the codebase:

    1. ``await db.execute(sql, params)``         — plain fire-and-forget
    2. ``async with db.execute(sql, params) as cursor:``  — SELECT with cursor

    This is achieved by implementing both ``__await__`` (so ``await`` works)
    and ``__aenter__``/``__aexit__`` (so ``async with`` works).
    """

    def __init__(self, pool, sql: str, params, learned) -> None:
        self._pool = pool
        self._sql = sql
        self._params = params
        self._learned = learned

    # -- awaitable (``await db.execute(...)``) -------------------------

    def __await__(self):
        return self._do_execute().__await__()

    async def _do_execute(self):
        async with self._pool.acquire() as conn:
            sql_stripped = self._sql.strip().upper()
            if sql_stripped.startswith(("SELECT", "WITH")):
                rows = await _run(conn.fetch, self._sql, self._params, self._learned)
                return _PostgresCursor([_Row(r) for r in rows])
            await _run(conn.execute, self._sql, self._params, self._learned)
            return _PostgresCursor([])

    # -- async context manager (``async with db.execute(...) as cur:``) --

    async def __aenter__(self) -> _PostgresCursor:
        async with self._pool.acquire() as conn:
            rows = await _run(conn.fetch, self._sql, self._params, self._learned)
        return _PostgresCursor([_Row(r) for r in rows])

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class _BoundConnection:
    """Connection facade used only inside its owning transaction/task."""

    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


class PostgresDB:
    """Drop-in async replacement for an aiosqlite connection.

    Wraps an asyncpg connection pool and exposes the same ``execute``,
    ``fetchone``, ``fetchall``, and ``executemany`` interface that the rest of
    the codebase relies on, so every store works unchanged with either backend.

    Automatically translates common SQLite idioms to PostgreSQL:
    - ``?`` placeholders → ``$1``, ``$2``, …
    - ``INSERT OR REPLACE INTO`` → ``INSERT INTO … ON CONFLICT DO UPDATE``
    - ``INSERT OR IGNORE INTO`` → ``INSERT INTO … ON CONFLICT DO NOTHING``
    - ``datetime('now')`` → ``NOW()``

    Date and time arguments bound as ISO text, or as aware datetimes for a
    column without a time zone, are converted to what the column takes (see
    ``_run``). ``executemany`` is not covered.
    """

    def __init__(self, pool, _learned: dict | None = None) -> None:
        self._pool = pool
        # Statement -> {argument index: conversion}, shared with transactions.
        self._learned: dict = {} if _learned is None else _learned

    @property
    def pool(self):
        return self._pool

    @asynccontextmanager
    async def transaction(self):
        """Yield a separate facade pinned to one connection until commit/rollback.

        The root pool facade keeps its existing autocommit behavior. Callers must
        use the yielded facade for every statement in the transaction.
        """
        async with self._pool.acquire(timeout=10) as connection:
            async with connection.transaction():
                yield PostgresDB(_BoundConnection(connection), self._learned)

    # ------------------------------------------------------------------
    # Public interface (mirrors aiosqlite.Connection)
    # ------------------------------------------------------------------

    def execute(self, sql: str, params=None) -> _PostgresContextManager:
        """Execute a SQL statement.

        Returns a :class:`_PostgresContextManager` that is **both** awaitable
        (``await db.execute(...)``) and an async context manager
        (``async with db.execute(...) as cursor:``), matching the dual
        interface that aiosqlite exposes.
        """
        sql = self._translate(sql)
        return _PostgresContextManager(self._pool, sql, params, self._learned)

    async def fetchone(self, sql: str, params=None) -> dict | None:
        sql = self._translate(sql)
        async with self._pool.acquire() as conn:
            row = await _run(conn.fetchrow, sql, params, self._learned)
            return _Row(row) if row else None

    async def fetchall(self, sql: str, params=None) -> list[dict]:
        sql = self._translate(sql)
        async with self._pool.acquire() as conn:
            rows = await _run(conn.fetch, sql, params, self._learned)
            return [_Row(r) for r in rows]

    async def fetch(self, sql: str, *args) -> list[dict]:
        """asyncpg-compatible fetch with positional args.

        The arena/escape-room store code uses ``await db.fetch(sql, *params)``
        (asyncpg native style) rather than ``db.fetchall(sql, list_of_params)``.
        """
        return await self.fetchall(sql, list(args) if args else None)

    async def executemany(self, sql: str, params_list) -> None:
        sql = self._translate(sql)
        async with self._pool.acquire() as conn:
            await conn.executemany(sql, params_list)

    async def executescript(self, sql: str) -> None:
        """Execute multiple statements separated by semicolons."""
        sql = self._translate(sql)
        async with self._pool.acquire() as conn:
            await conn.execute(sql)

    async def commit(self) -> None:
        """No-op — asyncpg auto-commits each statement."""
        pass

    # ------------------------------------------------------------------
    # SQL translation layer
    # ------------------------------------------------------------------

    @classmethod
    def _translate(cls, sql: str) -> str:
        """Translate SQLite SQL to PostgreSQL."""
        translated = cls._after_upsert(cls._convert_insert_or_replace(sql))
        first_column = cls._after_upsert(
            cls._convert_insert_or_replace(sql, first_column=True)
        )
        if first_column != translated and len(_FIRST_COLUMN_UPSERTS) < _MAX_LEARNED_STATEMENTS:
            _FIRST_COLUMN_UPSERTS[translated] = first_column
        return translated

    @classmethod
    def _after_upsert(cls, sql: str) -> str:
        sql = cls._convert_insert_or_ignore(sql)
        sql = cls._convert_autoincrement(sql)
        sql = cls._convert_datetime_now(sql)
        return cls._convert_placeholders(sql)

    @staticmethod
    def _convert_placeholders(sql: str) -> str:
        """Convert SQLite ``?`` placeholders to PostgreSQL ``$1``, ``$2``, …"""
        parts = sql.split("?")
        if len(parts) == 1:
            return sql
        result = parts[0]
        for i in range(1, len(parts)):
            result += f"${i}" + parts[i]
        return result

    # INSERT OR REPLACE replaces on a table's unique key. PostgreSQL has to be
    # told which columns that is. Without an entry here it is taken to be the
    # first column listed, which is only right when that column alone is the
    # key. A table whose key is several columns, or whose statement builds its
    # column list at run time, needs an entry.
    # tests/unit/test_storage/test_upsert_keys.py checks every statement.
    _CONFLICT_KEYS: dict[str, list[str]] = {
        "strategy_confidence_calibration": [
            "agent_name",
            "confidence_bucket",
            "window_label",
        ],
        "consensus_votes": ["symbol", "side", "agent_name"],
        "bittensor_accuracy_records": ["window_id", "miner_hotkey"],
        "bittensor_miner_rankings": ["miner_hotkey", "symbol"],
        "trade_analytics": ["tracked_position_id"],
    }

    @classmethod
    def _convert_insert_or_replace(cls, sql: str, first_column: bool = False) -> str:
        """Convert INSERT OR REPLACE INTO t (...) VALUES (...) →
        INSERT INTO t (...) VALUES (...) ON CONFLICT DO UPDATE SET ..."""
        m = re.match(
            r"\s*INSERT\s+OR\s+REPLACE\s+INTO\s+([\w.]+)\s*\(([^)]+)\)",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return sql
        table = m.group(1)
        # If schema-prefixed, use only the table name for the key lookup
        table_name_only = table.split(".")[-1]
        cols = [c.strip() for c in m.group(2).split(",")]
        pk_cols = (
            [cols[0]]
            if first_column
            else cls._CONFLICT_KEYS.get(table_name_only, [cols[0]])
        )
        pk_set = set(pk_cols)
        pk_clause = ", ".join(pk_cols)
        update_cols = [c for c in cols if c not in pk_set]
        if not update_cols:
            update_cols = cols
        set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
        # Replace the INSERT OR REPLACE with standard INSERT
        new_sql = re.sub(
            r"INSERT\s+OR\s+REPLACE\s+INTO",
            "INSERT INTO",
            sql,
            count=1,
            flags=re.IGNORECASE,
        )
        # Append ON CONFLICT clause
        new_sql = new_sql.rstrip().rstrip(";")
        new_sql += f" ON CONFLICT ({pk_clause}) DO UPDATE SET {set_clause}"
        return new_sql

    @staticmethod
    def _convert_insert_or_ignore(sql: str) -> str:
        """Convert INSERT OR IGNORE INTO → INSERT INTO ... ON CONFLICT DO NOTHING"""
        if not re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", sql, re.IGNORECASE):
            return sql
        new_sql = re.sub(
            r"INSERT\s+OR\s+IGNORE\s+INTO",
            "INSERT INTO",
            sql,
            count=1,
            flags=re.IGNORECASE,
        )
        new_sql = new_sql.rstrip().rstrip(";")
        new_sql += " ON CONFLICT DO NOTHING"
        return new_sql

    @staticmethod
    def _convert_autoincrement(sql: str) -> str:
        """Convert INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY."""
        return re.sub(
            r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
            "SERIAL PRIMARY KEY",
            sql,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _convert_datetime_now(sql: str) -> str:
        """Convert SQLite datetime functions to PostgreSQL equivalents.

        Handles:
          datetime('now')                → NOW()
          datetime('now', '-2 minutes')   → NOW() - INTERVAL '2 minutes'
          datetime('now', '+1 hour')      → NOW() + INTERVAL '1 hour'
        """

        def _replace_datetime_modifier(match: re.Match) -> str:
            modifier = match.group(1).strip()
            mod_match = re.match(r"^([+-])(\d+)\s+(\w+)$", modifier)
            if mod_match:
                sign, amount, unit = mod_match.groups()
                pg_sign = "-" if sign == "-" else "+"
                return f"NOW() {pg_sign} INTERVAL '{amount} {unit}'"
            return match.group(0)

        sql = re.sub(
            r"datetime\s*\(\s*'now'\s*,\s*'([^']+)'\s*\)",
            _replace_datetime_modifier,
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(r"datetime\s*\(\s*'now'\s*\)", "NOW()", sql, flags=re.IGNORECASE)
        return sql
