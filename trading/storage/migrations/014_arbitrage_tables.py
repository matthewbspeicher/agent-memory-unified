from __future__ import annotations
import aiosqlite


async def upgrade(db: aiosqlite.Connection) -> None:
    # 1. Arbitrage Trades Table
    await db.execute(
        """CREATE TABLE IF NOT EXISTS arb_trades (
            id TEXT PRIMARY KEY,
            symbol_a TEXT NOT NULL,
            symbol_b TEXT NOT NULL,
            expected_profit_bps INTEGER NOT NULL,
            sequencing TEXT NOT NULL,
            state TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )

    # 2. Arbitrage Legs Table
    await db.execute(
        """CREATE TABLE IF NOT EXISTS arb_legs (
            trade_id TEXT NOT NULL,
            leg_name TEXT NOT NULL, -- 'leg_a' or 'leg_b'
            broker_id TEXT NOT NULL,
            order_data TEXT NOT NULL, -- JSON serialized OrderBase
            fill_price TEXT,
            fill_quantity TEXT NOT NULL,
            status TEXT NOT NULL,
            external_order_id TEXT,
            PRIMARY KEY (trade_id, leg_name),
            FOREIGN KEY (trade_id) REFERENCES arb_trades(id) ON DELETE CASCADE
        )"""
    )

    # Indices for performance
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_arb_trades_state ON arb_trades(state)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_arb_legs_trade_id ON arb_legs(trade_id)"
    )


async def downgrade(db: aiosqlite.Connection) -> None:
    await db.execute("DROP TABLE IF EXISTS arb_legs")
    await db.execute("DROP TABLE IF EXISTS arb_trades")
