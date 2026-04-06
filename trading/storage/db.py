from __future__ import annotations
import logging
import ssl as _ssl
import aiosqlite
from storage.postgres import PostgresDB
from config import Config

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Database connection manager that accepts Config parameter.

    Handles both SQLite and PostgreSQL connections based on config.database_url.
    """

    def __init__(self, config: Config):
        self.config = config
        self.connection = None

    async def connect(self):
        """
        Establish database connection based on configuration.

        Returns:
            Either an aiosqlite.Connection or PostgresDB instance
        """
        if self.config.database_url:
            # PostgreSQL mode
            import asyncpg  # optional dependency

            if self.config.database_ssl:
                ssl_ctx = _ssl.create_default_context()
                if not self.config.database_ssl_verify:
                    ssl_ctx.check_hostname = False
                    ssl_ctx.verify_mode = _ssl.CERT_NONE
            else:
                ssl_ctx = None

            pool = await asyncpg.create_pool(
                self.config.database_url,
                ssl=ssl_ctx,
                statement_cache_size=0,
            )
            self.connection = PostgresDB(pool)
            # DISABLED: Laravel now owns all DDL via migrations
            # await run_migrations(self.connection)
            logger.info("Connected to PostgreSQL (DDL managed by Laravel)")
            return self.connection

        # SQLite mode
        self.connection = await aiosqlite.connect(self.config.db_path or "data.db")
        self.connection.row_factory = aiosqlite.Row
        await init_db(self.connection)
        return self.connection

    async def close(self):
        """Close the database connection"""
        if self.connection is None:
            return

        if hasattr(self.connection, "pool"):
            # PostgresDB
            await self.connection.pool.close()
        else:
            # aiosqlite
            await self.connection.close()

    async def __aenter__(self):
        """Async context manager entry"""
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


async def init_db(db: aiosqlite.Connection) -> None:
    pass  # DISABLED: Laravel now owns all DDL via migrations


async def get_db(path: str = "data.db") -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await init_db(db)
    return db


async def create_db(config: Config):
    """
    Create and return a database connection.

    Returns either an aiosqlite connection or a :class:`~storage.postgres.PostgresDB`
    depending on whether ``config.database_url`` is set.

    Args:
        config: Config instance with database settings

    Returns:
        Database connection (aiosqlite.Connection or PostgresDB)

    Usage::

        from config import load_config
        config = load_config()
        db = await create_db(config)
        app.state.db = db
    """
    db_conn = DatabaseConnection(config)
    return await db_conn.connect()
