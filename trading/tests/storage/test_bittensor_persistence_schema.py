"""
Tests for Bittensor persistence schema.
"""

import pytest
import aiosqlite
from storage.db import init_db


@pytest.mark.asyncio
async def test_bittensor_processed_positions_table_exists():
    """Verify that bittensor_processed_positions table is created during init_db."""
    async with aiosqlite.connect(":memory:") as db:
        await init_db(db)

        # Check if table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bittensor_processed_positions'"
        )
        row = await cursor.fetchone()
        assert row is not None, "bittensor_processed_positions table should exist"

        # Check columns
        cursor = await db.execute("PRAGMA table_info(bittensor_processed_positions)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        assert "position_uuid" in column_names
        assert "miner_hotkey" in column_names
        assert "processed_at" in column_names
