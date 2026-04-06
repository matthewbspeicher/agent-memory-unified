from __future__ import annotations
import aiosqlite


async def upgrade(db: aiosqlite.Connection) -> None:
    # Add locking columns to arb_spread_observations
    try:
        await db.execute(
            "ALTER TABLE arb_spread_observations ADD COLUMN is_claimed BOOLEAN DEFAULT 0"
        )
        await db.execute(
            "ALTER TABLE arb_spread_observations ADD COLUMN claimed_at TEXT"
        )
        await db.execute(
            "ALTER TABLE arb_spread_observations ADD COLUMN claimed_by TEXT"
        )
    except Exception:
        # Columns might already exist if migration was partially run
        pass


async def downgrade(db: aiosqlite.Connection) -> None:
    # SQLite doesn't support DROP COLUMN easily, so we usually just leave them
    pass
