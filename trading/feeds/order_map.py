"""Maps Polymarket order hashes back to originating signal_ids.

Polymarket EIP-712 orders do not round-trip a free-text identifier, so we
must persist the (order_hash -> signal_id) mapping ourselves to attribute
fills back to the signal that produced them.
"""

from __future__ import annotations

import asyncpg


class OrderMap:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record(self, *, order_hash: str, signal_id: str, venue: str) -> None:
        """Persist an order_hash -> signal_id mapping. First write wins (idempotent)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO signal_order_map (order_hash, signal_id, venue)
                VALUES ($1, $2, $3)
                ON CONFLICT (order_hash) DO NOTHING
                """,
                order_hash,
                signal_id,
                venue,
            )

    async def lookup(self, order_hash: str) -> str | None:
        """Return the signal_id for a given order_hash, or None if not mapped."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT signal_id FROM signal_order_map WHERE order_hash = $1",
                order_hash,
            )
            return row["signal_id"] if row else None
