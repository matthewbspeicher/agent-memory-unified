"""Storage acquisition and sanitized initialization observations."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from config import Config
from storage.db import DatabaseConnection, get_db, init_db, init_db_postgres
from storage.initialization import InitializationReport


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [RuntimeError("initialize"), asyncio.CancelledError()]
)
async def test_sqlite_initialization_failure_releases_acquisition(failure):
    manager = DatabaseConnection(Config(db_path=":memory:"))
    captured = []

    async def fail(db, **kwargs):
        captured.append(db)
        raise failure

    with patch("storage.db.init_db", side_effect=fail):
        with pytest.raises(type(failure)) as raised:
            await manager.connect()
    assert raised.value is failure
    assert manager.connection is None
    with pytest.raises(ValueError):
        await captured[0].execute("SELECT 1")
    await manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [RuntimeError("initialize"), asyncio.CancelledError()]
)
async def test_get_db_failure_releases_acquisition(failure):
    captured = []

    async def fail(db, **kwargs):
        captured.append(db)
        raise failure

    with patch("storage.db.init_db", side_effect=fail):
        with pytest.raises(type(failure)) as raised:
            await get_db(":memory:")
    assert raised.value is failure
    with pytest.raises(ValueError):
        await captured[0].execute("SELECT 1")


@pytest.mark.asyncio
async def test_failed_initialization_preserves_primary_error_when_close_fails():
    manager = DatabaseConnection(Config(db_path=":memory:"))
    failure = RuntimeError("primary")
    db = AsyncMock(spec=aiosqlite.Connection)
    # execute returns an awaitable context manager; mock it explicitly across
    # Python/aiosqlite versions so PRAGMA setup reaches the injected failure.
    db.execute = AsyncMock()
    db.close.side_effect = OSError("cleanup")
    with patch("storage.db.aiosqlite.connect", new=AsyncMock(return_value=db)):
        with patch("storage.db.init_db", side_effect=failure):
            with pytest.raises(RuntimeError) as raised:
                await manager.connect()
    assert raised.value is failure
    assert manager.connection is None
    db.close.assert_awaited_once()
    await manager.close()
    db.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_context_body_failure_is_not_masked_by_cleanup():
    manager = DatabaseConnection(Config(db_path=":memory:"))
    db = AsyncMock(spec=aiosqlite.Connection)
    db.execute = AsyncMock()
    db.close.side_effect = OSError("cleanup")
    failure = ValueError("body")
    with patch("storage.db.aiosqlite.connect", new=AsyncMock(return_value=db)):
        with patch("storage.db.init_db", new=AsyncMock()):
            with pytest.raises(ValueError) as raised:
                async with manager:
                    raise failure
    assert raised.value is failure


@pytest.mark.asyncio
async def test_successful_connection_close_is_idempotent():
    manager = DatabaseConnection(Config(db_path=":memory:"))
    with patch("storage.db.init_db", new=AsyncMock()):
        db = await manager.connect()
        assert await manager.connect() is db
    await manager.close()
    await manager.close()
    assert manager.connection is None
    with pytest.raises(ValueError):
        await db.execute("SELECT 1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [RuntimeError("initialize"), asyncio.CancelledError()]
)
async def test_postgres_initialization_failure_closes_pool(failure):
    pool = MagicMock()
    pool.close = AsyncMock()
    manager = DatabaseConnection(Config(database_url="postgresql://local/test"))
    with patch("asyncpg.create_pool", new=AsyncMock(return_value=pool)):
        with patch("storage.db.init_db_postgres", side_effect=failure):
            with pytest.raises(type(failure)) as raised:
                await manager.connect()
    assert raised.value is failure
    pool.close.assert_awaited_once()
    assert manager.connection is None
    await manager.close()
    pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_facade_failure_still_closes_acquired_pool():
    pool = MagicMock()
    pool.close = AsyncMock()
    manager = DatabaseConnection(Config(database_url="postgresql://local/test"))
    with patch("asyncpg.create_pool", new=AsyncMock(return_value=pool)):
        with patch("storage.db.PostgresDB", side_effect=RuntimeError("facade")):
            with pytest.raises(RuntimeError, match="facade"):
                await manager.connect()
    pool.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [False, True])
async def test_pool_close_failure_forces_termination_and_clears_owner(timeout):
    pool = MagicMock()
    if timeout:

        async def blocked():
            await asyncio.Event().wait()

        pool.close = AsyncMock(side_effect=blocked)
    else:
        pool.close = AsyncMock(side_effect=OSError("cleanup"))
    manager = DatabaseConnection(Config())
    manager._pool = pool
    manager.connection = object()
    with patch("storage.db._POOL_CLOSE_TIMEOUT_SECONDS", 0.01):
        with pytest.raises(TimeoutError if timeout else OSError):
            await manager.close()
    pool.terminate.assert_called_once()
    assert manager.connection is None
    await manager.close()
    pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_sqlite_existing_columns_do_not_produce_issues():
    report = InitializationReport()
    async with aiosqlite.connect(":memory:") as db:
        assert await init_db(db, diagnostics=report) is None
        assert await init_db(db, diagnostics=report) is None
    assert report.issues == []


@pytest.mark.asyncio
async def test_sqlite_unexpected_optional_and_migration_failures_are_visible():
    report = InitializationReport()
    db = MagicMock()
    db.executescript = AsyncMock(side_effect=[None, OSError("private DSN")])
    db.execute = AsyncMock(side_effect=aiosqlite.OperationalError("permission denied"))
    assert await init_db(db, diagnostics=report) is None
    assert report.issues[0].step == "sqlite.feed_tables"
    assert report.issues[0].error_type == "OSError"
    assert any(
        issue.step == "sqlite.tracked_positions.account_id" for issue in report.issues
    )
    assert "private DSN" not in repr(report)
    assert "permission denied" not in repr(report)


class DuplicateColumn(Exception):
    sqlstate = "42701"


@pytest.mark.asyncio
async def test_postgres_duplicate_columns_are_expected_but_other_errors_recorded():
    report = InitializationReport()
    db = MagicMock()

    async def execute(sql):
        if sql.startswith("ALTER TABLE") and "ADD COLUMN" in sql:
            if "tracked_positions ADD COLUMN account_id" in sql:
                raise PermissionError("private DSN")
            raise DuplicateColumn("already exists")
        if sql.startswith("CREATE INDEX IF NOT EXISTS idx_arb_spread_pair"):
            raise RuntimeError("index denied")
        if sql.startswith("UPDATE opportunities SET created_at"):
            raise RuntimeError("fixup denied")

    db.execute = AsyncMock(side_effect=execute)
    assert await init_db_postgres(db, diagnostics=report) is None
    steps = {issue.step for issue in report.issues}
    assert "postgres.tracked_positions.account_id" in steps
    assert "postgres.spread_index.1" in steps
    assert "postgres.opportunity_timestamps.1" in steps
    assert all(issue.error_type != "DuplicateColumn" for issue in report.issues)
    assert "private DSN" not in repr(report)


@pytest.mark.asyncio
async def test_manager_exposes_optional_initialization_issues_without_failing_connect():
    manager = DatabaseConnection(Config(db_path=":memory:"))

    async def initialize(db, *, diagnostics):
        diagnostics.record("optional.test", RuntimeError("private detail"))

    with patch("storage.db.init_db", side_effect=initialize):
        async with manager as db:
            row = await (await db.execute("SELECT 1")).fetchone()
            assert row[0] == 1
            assert manager.initialization.issues[0].step == "optional.test"
    assert "private detail" not in repr(manager.initialization)


@pytest.mark.asyncio
async def test_get_db_cleanup_failure_does_not_replace_initialization_error():
    db = AsyncMock(spec=aiosqlite.Connection)
    db.close.side_effect = OSError("cleanup")
    failure = RuntimeError("primary")
    with patch("storage.db.aiosqlite.connect", new=AsyncMock(return_value=db)):
        with patch("storage.db.init_db", side_effect=failure):
            with pytest.raises(RuntimeError) as raised:
                await get_db(":memory:")
    assert raised.value is failure
    db.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_cleanup_failure_does_not_replace_initialization_error():
    pool = MagicMock()
    pool.close = AsyncMock(side_effect=OSError("cleanup"))
    manager = DatabaseConnection(Config(database_url="postgresql://local/test"))
    failure = RuntimeError("primary")
    with patch("asyncpg.create_pool", new=AsyncMock(return_value=pool)):
        with patch("storage.db.init_db_postgres", side_effect=failure):
            with pytest.raises(RuntimeError) as raised:
                await manager.connect()
    assert raised.value is failure
    pool.close.assert_awaited_once()
    pool.terminate.assert_called_once()
    assert manager.connection is None


@pytest.mark.asyncio
async def test_timestamp_fixup_driver_errors_retain_debug_severity_and_diagnostics(
    caplog,
):
    from asyncpg import DatatypeMismatchError

    report = InitializationReport()
    db = MagicMock()

    async def execute(sql):
        if sql.startswith(
            ("UPDATE opportunities SET", "ALTER TABLE opportunities ALTER COLUMN")
        ):
            raise DatatypeMismatchError("private connection detail")

    db.execute = AsyncMock(side_effect=execute)
    with caplog.at_level("DEBUG", logger="storage.db"):
        assert await init_db_postgres(db, diagnostics=report) is None

    assert [issue.step for issue in report.issues] == [
        f"postgres.opportunity_timestamps.{number}" for number in range(1, 5)
    ]
    assert {issue.error_type for issue in report.issues} == {"DatatypeMismatchError"}
    assert "private connection detail" not in repr(report)
    assert not [record for record in caplog.records if record.levelno >= 30]
    assert (
        len([record for record in caplog.records if record.levelname == "DEBUG"]) == 4
    )
