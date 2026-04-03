"""
Tests for storage/db.py - DatabaseConnection accepts Config parameter
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiosqlite

from storage.db import DatabaseConnection
from config import Config


class TestDatabaseConnectionInit:
    """Test DatabaseConnection initialization"""

    def test_accepts_config_parameter(self):
        config = Config(db_path="test.db")
        db_conn = DatabaseConnection(config)
        assert db_conn.config == config

    def test_stores_config_db_path(self):
        config = Config(db_path="/path/to/data.db")
        db_conn = DatabaseConnection(config)
        assert db_conn.config.db_path == "/path/to/data.db"

    def test_stores_config_database_url(self):
        config = Config(database_url="postgresql://user:pass@host/db")
        db_conn = DatabaseConnection(config)
        assert db_conn.config.database_url == "postgresql://user:pass@host/db"


class TestDatabaseConnectionConnect:
    """Test DatabaseConnection.connect() method"""

    @pytest.mark.asyncio
    async def test_connect_sqlite_when_no_database_url(self):
        config = Config(db_path=":memory:")
        db_conn = DatabaseConnection(config)

        with patch("storage.db.aiosqlite.connect", new_callable=AsyncMock) as mock_connect:
            mock_db = AsyncMock(spec=aiosqlite.Connection)
            mock_connect.return_value = mock_db

            db = await db_conn.connect()

            mock_connect.assert_called_once_with(":memory:")
            assert db == mock_db
            assert db_conn.connection == mock_db

    @pytest.mark.asyncio
    async def test_connect_postgres_when_database_url_set(self):
        config = Config(
            database_url="postgresql://user:pass@host/db",
            database_ssl=False,
        )
        db_conn = DatabaseConnection(config)

        mock_pool = AsyncMock()
        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool) as mock_create_pool:
            with patch("storage.db.PostgresDB") as mock_postgres_cls:
                mock_postgres_db = MagicMock()
                mock_postgres_cls.return_value = mock_postgres_db

                with patch("storage.db.run_migrations", new_callable=AsyncMock) as mock_migrations:
                    db = await db_conn.connect()

                    mock_create_pool.assert_called_once()
                    assert mock_create_pool.call_args[0][0] == "postgresql://user:pass@host/db"
                    mock_postgres_cls.assert_called_once_with(mock_pool)
                    mock_migrations.assert_called_once_with(mock_postgres_db)
                    assert db == mock_postgres_db
                    assert db_conn.connection == mock_postgres_db

    @pytest.mark.asyncio
    async def test_connect_postgres_with_ssl(self):
        config = Config(
            database_url="postgresql://user:pass@host/db",
            database_ssl=True,
            database_ssl_verify=True,
        )
        db_conn = DatabaseConnection(config)

        mock_pool = AsyncMock()
        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool) as mock_create_pool:
            with patch("storage.db._ssl.create_default_context") as mock_ssl:
                mock_ssl_ctx = MagicMock()
                mock_ssl.return_value = mock_ssl_ctx

                with patch("storage.db.PostgresDB") as mock_postgres_cls:
                    mock_postgres_db = MagicMock()
                    mock_postgres_cls.return_value = mock_postgres_db

                    with patch("storage.db.run_migrations", new_callable=AsyncMock):
                        await db_conn.connect()

                        mock_ssl.assert_called_once()
                        # Verify SSL context was passed
                        call_kwargs = mock_create_pool.call_args[1]
                        assert call_kwargs["ssl"] == mock_ssl_ctx
                        assert call_kwargs["statement_cache_size"] == 0

    @pytest.mark.asyncio
    async def test_connect_postgres_ssl_verify_false(self):
        config = Config(
            database_url="postgresql://user:pass@host/db",
            database_ssl=True,
            database_ssl_verify=False,
        )
        db_conn = DatabaseConnection(config)

        mock_pool = AsyncMock()
        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool):
            with patch("storage.db._ssl.create_default_context") as mock_ssl:
                mock_ssl_ctx = MagicMock()
                mock_ssl.return_value = mock_ssl_ctx

                with patch("storage.db.PostgresDB"):
                    with patch("storage.db.run_migrations", new_callable=AsyncMock):
                        await db_conn.connect()

                        # Verify SSL verification was disabled
                        assert mock_ssl_ctx.check_hostname is False
                        assert mock_ssl_ctx.verify_mode == 0  # ssl.CERT_NONE


    @pytest.mark.asyncio
    async def test_connect_sets_row_factory_for_sqlite(self):
        config = Config(db_path=":memory:")
        db_conn = DatabaseConnection(config)

        with patch("storage.db.aiosqlite.connect", new_callable=AsyncMock) as mock_connect:
            mock_db = AsyncMock(spec=aiosqlite.Connection)
            mock_connect.return_value = mock_db

            with patch("storage.db.init_db", new_callable=AsyncMock):
                await db_conn.connect()

                # Check row_factory was set
                assert mock_db.row_factory == aiosqlite.Row

    @pytest.mark.asyncio
    async def test_connect_calls_init_db_for_sqlite(self):
        config = Config(db_path=":memory:")
        db_conn = DatabaseConnection(config)

        with patch("storage.db.aiosqlite.connect", new_callable=AsyncMock) as mock_connect:
            mock_db = AsyncMock(spec=aiosqlite.Connection)
            mock_connect.return_value = mock_db

            with patch("storage.db.init_db", new_callable=AsyncMock) as mock_init:
                await db_conn.connect()

                mock_init.assert_called_once_with(mock_db)

    @pytest.mark.asyncio
    async def test_connect_calls_migrations_for_postgres(self):
        config = Config(database_url="postgresql://user:pass@host/db")
        db_conn = DatabaseConnection(config)

        mock_pool = AsyncMock()
        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool):
            with patch("storage.db.PostgresDB") as mock_postgres_cls:
                mock_postgres_db = MagicMock()
                mock_postgres_cls.return_value = mock_postgres_db

                with patch("storage.db.run_migrations", new_callable=AsyncMock) as mock_migrations:
                    await db_conn.connect()

                    mock_migrations.assert_called_once_with(mock_postgres_db)


class TestDatabaseConnectionClose:
    """Test DatabaseConnection.close() method"""

    @pytest.mark.asyncio
    async def test_close_closes_sqlite_connection(self):
        config = Config(db_path=":memory:")
        db_conn = DatabaseConnection(config)

        mock_db = AsyncMock(spec=aiosqlite.Connection)
        db_conn.connection = mock_db

        await db_conn.close()

        mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_closes_postgres_pool(self):
        config = Config(database_url="postgresql://user:pass@host/db")
        db_conn = DatabaseConnection(config)

        mock_pool = AsyncMock()
        mock_postgres_db = MagicMock()
        mock_postgres_db.pool = mock_pool
        db_conn.connection = mock_postgres_db

        await db_conn.close()

        mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_handles_no_connection(self):
        config = Config(db_path=":memory:")
        db_conn = DatabaseConnection(config)

        # Should not raise even if never connected
        await db_conn.close()


class TestDatabaseConnectionContextManager:
    """Test DatabaseConnection as async context manager"""

    @pytest.mark.asyncio
    async def test_context_manager_connects_and_closes(self):
        config = Config(db_path=":memory:")
        db_conn = DatabaseConnection(config)

        with patch("storage.db.aiosqlite.connect", new_callable=AsyncMock) as mock_connect:
            mock_db = AsyncMock(spec=aiosqlite.Connection)
            mock_connect.return_value = mock_db

            with patch("storage.db.init_db", new_callable=AsyncMock):
                async with db_conn as db:
                    assert db == mock_db
                    mock_connect.assert_called_once()

                # After exiting context, close should be called
                mock_db.close.assert_called_once()
