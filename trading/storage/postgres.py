from __future__ import annotations

import re


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

    def __init__(self, pool, sql: str, params) -> None:
        self._pool = pool
        self._sql = sql
        self._params = params

    # -- awaitable (``await db.execute(...)``) -------------------------

    def __await__(self):
        return self._do_execute().__await__()

    async def _do_execute(self):
        async with self._pool.acquire() as conn:
            sql_stripped = self._sql.strip().upper()
            if sql_stripped.startswith(("SELECT", "WITH")):
                rows = await conn.fetch(self._sql, *(self._params or []))
                return _PostgresCursor([dict(r) for r in rows])
            await conn.execute(self._sql, *(self._params or []))
            return _PostgresCursor([])

    # -- async context manager (``async with db.execute(...) as cur:``) --

    async def __aenter__(self) -> _PostgresCursor:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(self._sql, *(self._params or []))
        return _PostgresCursor([dict(r) for r in rows])

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


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
    """

    def __init__(self, pool) -> None:
        self._pool = pool

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
        return _PostgresContextManager(self._pool, sql, params)

    async def fetchone(self, sql: str, params=None) -> dict | None:
        sql = self._translate(sql)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, *(params or []))
            return dict(row) if row else None

    async def fetchall(self, sql: str, params=None) -> list[dict]:
        sql = self._translate(sql)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *(params or []))
            return [dict(r) for r in rows]

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
        sql = cls._convert_insert_or_replace(sql)
        sql = cls._convert_insert_or_ignore(sql)
        sql = cls._convert_datetime_now(sql)
        sql = cls._convert_placeholders(sql)
        return sql

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

    # Tables with composite primary keys — used by _convert_insert_or_replace
    # to generate the correct ON CONFLICT clause.
    _COMPOSITE_PKS: dict[str, list[str]] = {
        "strategy_confidence_calibration": [
            "agent_name",
            "confidence_bucket",
            "window_label",
        ],
        "consensus_votes": ["symbol", "side", "agent_name"],
    }

    @classmethod
    def _convert_insert_or_replace(cls, sql: str) -> str:
        """Convert INSERT OR REPLACE INTO t (...) VALUES (...) →
        INSERT INTO t (...) VALUES (...) ON CONFLICT DO UPDATE SET ..."""
        m = re.match(
            r"\s*INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return sql
        table = m.group(1)
        cols = [c.strip() for c in m.group(2).split(",")]
        # Use composite PK if known, else assume first column is the PK
        pk_cols = cls._COMPOSITE_PKS.get(table, [cols[0]])
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
    def _convert_datetime_now(sql: str) -> str:
        """Convert datetime('now') → NOW()"""
        return re.sub(r"datetime\s*\(\s*'now'\s*\)", "NOW()", sql, flags=re.IGNORECASE)
