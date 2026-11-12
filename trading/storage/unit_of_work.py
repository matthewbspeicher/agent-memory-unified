"""One owned database transaction, shared by the stores that commit together.

SQLite stores use a dedicated connection and BEGIN IMMEDIATE. PostgreSQL stores
pin one pooled connection and take a transaction-scoped advisory lock shared by
every process using the database. A transaction is re-entrant for the task that
owns it and never commits or rolls back another caller's work.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import aiosqlite

from storage.postgres import PostgresDB


class PaperWriteNotStarted(RuntimeError):
    """Admission failed before a paper transaction could mutate any state."""


class UnitOfWork:
    def __init__(self, db=None):
        self._db = db
        self._owns_db = False
        self._closed = False
        self._lock = asyncio.Lock()
        self._transaction_owner = None
        self._transaction_db = None
        self.is_postgres = not isinstance(db, aiosqlite.Connection) if db else False

    async def handle(self):
        """The handle to run statements on: the open transaction's, if the caller owns it."""
        if self._closed:
            raise RuntimeError("PaperStore is closed")
        if self._transaction_owner is asyncio.current_task():
            return self._transaction_db or self._db
        if self._db:
            return self._db
        from storage.db import get_db

        return await get_db()

    async def close(self) -> None:
        async with self._lock:
            if self._owns_db and self._db:
                await self._db.close()
            self._closed = True

    @property
    def owns_connection(self) -> bool:
        return self._owns_db

    async def supports_transactions(self) -> bool:
        return isinstance(await self.handle(), (aiosqlite.Connection, PostgresDB))

    @asynccontextmanager
    async def exclusive(self):
        """Hold the unit of work's lock without opening a transaction."""
        async with self._lock:
            yield

    async def adopt_dedicated_connection(self, source=None, *, busy_timeout: bool) -> bool:
        """Switch a file-backed SQLite store to its own connection, once.

        A dedicated connection keeps this unit of work from committing another
        store's statements. In-memory databases cannot be reopened and are kept.
        """
        db = self._db if source is None else source
        if not isinstance(db, aiosqlite.Connection) or self._owns_db:
            return False
        rows = await (await db.execute("PRAGMA database_list")).fetchall()
        filename = next((row[2] for row in rows if row[1] == "main"), "")
        if not filename:
            return False
        self._db = await aiosqlite.connect(filename)
        self._db.row_factory = aiosqlite.Row
        self._owns_db = True
        if busy_timeout:
            await self._db.execute("PRAGMA busy_timeout=5000")
        return True

    @asynccontextmanager
    async def transaction(self):
        """One owned transaction; never commit/rollback another caller's work."""
        task = asyncio.current_task()
        if self._transaction_owner is task:
            yield await self.handle()
            return
        async with self._lock:
            db = await self.handle()
            if isinstance(db, PostgresDB):
                started = False
                try:
                    async with db.transaction() as bound:
                        # Shared across stores/processes in this database. Reads
                        # use READ COMMITTED snapshots taken after lock acquisition.
                        await bound.execute("SET LOCAL lock_timeout = '5s'")
                        await bound.execute("SELECT pg_advisory_xact_lock(718302641)")
                        self._transaction_owner = task
                        self._transaction_db = bound
                        started = True
                        try:
                            yield bound
                        finally:
                            self._transaction_owner = None
                            self._transaction_db = None
                except Exception as exc:
                    if not started:
                        raise PaperWriteNotStarted(
                            "Paper database admission failed; no order was written"
                        ) from exc
                    raise
                return
            if not isinstance(db, aiosqlite.Connection):
                raise PaperWriteNotStarted(
                    "Paper transactions require supported transactional storage"
                )
            if db.in_transaction:
                raise PaperWriteNotStarted(
                    "Paper connection already has an unrelated transaction"
                )
            try:
                await db.execute("BEGIN IMMEDIATE")
            except aiosqlite.OperationalError as exc:
                raise PaperWriteNotStarted(
                    "Paper database is busy; no order was written"
                ) from exc
            self._transaction_owner = task
            self._transaction_db = db
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise
            finally:
                self._transaction_owner = None
                self._transaction_db = None
