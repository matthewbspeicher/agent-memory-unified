"""Engine connections keep timestamp defaults in UTC without changing stored data.

A disposable role has a non-UTC default, unlike the CI server's usual UTC.
Only schema bootstrap is replaced: the real DatabaseConnection/asyncpg pool,
facade, pool reset and connection replacement paths are exercised.
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest

from config import Config
from storage.db import DatabaseConnection

pytestmark = pytest.mark.integration


@pytest.fixture(params=[False, True], ids=["role-default", "dsn-override"])
async def engine(request):
    dsn = os.environ.get("AMU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail("AMU_TEST_POSTGRES_DSN must identify a disposable test database")
    token = uuid4().hex
    role, schema, password = "utc_role_" + token, "utc_schema_" + token, uuid4().hex
    app_name = "utc-test-" + token
    admin = await asyncpg.connect(dsn)
    manager = None
    role_created = False
    try:
        # Generated identifiers and password, on the disposable test server only.
        await admin.execute(f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{password}'")
        role_created = True
        await admin.execute(f"ALTER ROLE \"{role}\" SET TimeZone TO 'Asia/Tokyo'")
        await admin.execute(f'ALTER ROLE "{role}" SET search_path TO "{schema}"')
        await admin.execute(f'CREATE SCHEMA "{schema}" AUTHORIZATION "{role}"')
        parts = urlsplit(dsn)
        query = dict(parse_qsl(parts.query))
        query["application_name"] = app_name
        default_zone = "Asia/Tokyo"
        if request.param:
            query["TimeZone"] = "Pacific/Honolulu"
            default_zone = "Pacific/Honolulu"
        role_dsn = urlunsplit(
            (
                parts.scheme,
                f"{role}:{password}@{parts.hostname}:{parts.port or 5432}",
                parts.path,
                urlencode(query),
                parts.fragment,
            )
        )
        raw = await asyncpg.connect(role_dsn)
        try:
            assert await raw.fetchval("SHOW TimeZone") == default_zone
            await raw.execute("""CREATE TABLE moments (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                instant TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                day DATE NOT NULL DEFAULT CURRENT_DATE,
                explicit_utc TIMESTAMP,
                note TEXT
            )""")
            # Existing values must not be reinterpreted, migrated or overwritten.
            await raw.execute(
                "INSERT INTO moments (id, created_at, note) VALUES ('legacy', TIMESTAMP '2020-01-02 03:04:05', 'preserve')"
            )
        finally:
            await raw.close()
        manager = DatabaseConnection(
            Config(database_url=role_dsn, database_ssl=False, paper_trading=True)
        )
        # This test isolates connection policy from the separately documented
        # bootstrap-DDL incompatibility. No app schema migration is introduced.
        with patch("storage.db.init_db_postgres", new_callable=AsyncMock) as bootstrap:
            db = await manager.connect()
            bootstrap.assert_awaited_once_with(db)
            yield SimpleNamespace(
                manager=manager,
                db=db,
                dsn=role_dsn,
                schema=schema,
                app_name=app_name,
                default_zone=default_zone,
            )
    finally:
        if manager is not None:
            await manager.close()
        if role_created:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.execute(f'DROP ROLE "{role}"')
        await admin.close()


async def assert_defaults(db, row_id):
    stamp = datetime.now(timezone.utc)
    await db.execute(
        "INSERT INTO moments (id, explicit_utc) VALUES (?, ?)",
        (row_id, stamp.isoformat()),
    )
    row = await db.fetchone("SELECT * FROM moments WHERE id = ?", (row_id,))
    assert row["created_at"] == row["instant"].astimezone(timezone.utc).replace(
        tzinfo=None
    )
    assert row["day"] == row["instant"].astimezone(timezone.utc).date()
    assert row["explicit_utc"] == stamp.replace(tzinfo=None)
    legacy = await db.fetchone(
        "SELECT created_at, note FROM moments WHERE id = 'legacy'"
    )
    assert legacy["created_at"] == datetime(2020, 1, 2, 3, 4, 5)
    assert legacy["note"] == "preserve"


async def test_every_borrowed_engine_session_is_utc_and_other_settings_survive(engine):
    async with engine.db.pool.acquire() as first, engine.db.pool.acquire() as second:
        assert first.get_server_pid() != second.get_server_pid()
        for connection in (first, second):
            assert await connection.fetchval("SHOW TimeZone") == "UTC"
            assert await connection.fetchval("SHOW application_name") == engine.app_name
            assert await connection.fetchval("SELECT current_schema()") == engine.schema
    await assert_defaults(engine.db, "fresh")


async def test_pool_reset_restores_startup_utc_after_a_borrower_changes_timezone(
    engine,
):
    async with engine.db.pool.acquire() as connection:
        await connection.execute("SET TIME ZONE 'America/New_York'")
        assert await connection.fetchval("SHOW TimeZone") == "America/New_York"
    async with engine.db.pool.acquire() as reused:
        assert await reused.fetchval("SHOW TimeZone") == "UTC"
        await reused.execute("RESET ALL")
        assert await reused.fetchval("SHOW TimeZone") == "UTC"
    await assert_defaults(engine.db, "reset")


async def test_replaced_connections_and_transaction_defaults_still_use_utc(engine):
    async with engine.db.pool.acquire() as old:
        old_pid = old.get_server_pid()
    await engine.db.pool.expire_connections()
    async with engine.db.pool.acquire() as new:
        assert new.get_server_pid() != old_pid
        assert await new.fetchval("SHOW TimeZone") == "UTC"
    async with engine.db.transaction() as tx:
        assert (await tx.fetchone("SHOW TimeZone"))[0] == "UTC"
        await assert_defaults(tx, "transaction")


async def test_reopening_engine_does_not_change_role_defaults_or_existing_rows(engine):
    await engine.manager.close()
    raw = await asyncpg.connect(engine.dsn)
    try:
        # Pinning is session-local; the database/role policy was not rewritten.
        assert await raw.fetchval("SHOW TimeZone") == engine.default_zone
        assert (
            await raw.fetchval("SELECT note FROM moments WHERE id='legacy'")
            == "preserve"
        )
    finally:
        await raw.close()
    db = await engine.manager.connect()
    assert (await db.fetchone("SHOW TimeZone"))[0] == "UTC"
    await assert_defaults(db, "reopened")
