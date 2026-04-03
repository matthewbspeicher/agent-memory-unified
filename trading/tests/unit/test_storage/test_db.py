import pytest
import aiosqlite
from storage.db import init_db, get_db


class TestInitDb:
    async def test_creates_tables(self):
        db = await aiosqlite.connect(":memory:")
        await init_db(db)

        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in await cursor.fetchall()}
        assert "opportunities" in tables
        assert "trades" in tables
        assert "risk_events" in tables
        await db.close()

    async def test_idempotent(self):
        db = await aiosqlite.connect(":memory:")
        await init_db(db)
        await init_db(db)  # should not raise
        await db.close()

    async def test_learning_tables_created(self):
        db = await aiosqlite.connect(":memory:")
        await init_db(db)

        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in await cursor.fetchall()}
        assert "tracked_positions" in tables
        assert "trust_events" in tables
        assert "agent_overrides" in tables
        assert "backtest_results" in tables
        assert "tournament_rounds" in tables
        assert "tournament_variants" in tables
        assert "llm_lessons" in tables
        assert "llm_prompt_versions" in tables
        await db.close()

    async def test_shadow_execution_table_created(self):
        db = await aiosqlite.connect(":memory:")
        await init_db(db)

        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in await cursor.fetchall()}
        assert "shadow_executions" in tables

        columns = await db.execute("PRAGMA table_info(shadow_executions)")
        column_names = {row[1] for row in await columns.fetchall()}
        assert "decision_status" in column_names
        assert "resolve_after" in column_names
        assert "resolution_status" in column_names

        indexes = await db.execute("PRAGMA index_list(shadow_executions)")
        index_names = {row[1] for row in await indexes.fetchall()}
        assert "idx_shadow_executions_due" in index_names
        assert "idx_shadow_executions_agent_opened" in index_names
        await db.close()


@pytest.mark.asyncio
async def test_get_db_custom_path(tmp_path):
    db_path = str(tmp_path / "custom.db")
    db = await get_db(db_path)
    try:
        tables = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        rows = await tables.fetchall()
        assert len(rows) > 0
    finally:
        await db.close()
