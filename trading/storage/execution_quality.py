"""ExecutionQualityStore — persists execution fill data to SQLite."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite
    from execution.tracker import ExecutionFill

logger = logging.getLogger(__name__)


class ExecutionQualityStore:
    """Persists ExecutionFill records to the execution_quality table."""

    def __init__(self, db: "aiosqlite.Connection") -> None:
        self._db = db

    async def save(self, fill: "ExecutionFill") -> None:
        """Save a fill record to the database."""
        await self._db.execute(
            """
            INSERT INTO execution_quality
                (opportunity_id, agent_name, broker_id, symbol, side,
                 expected_price, actual_price, quantity, slippage_bps, filled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fill.opportunity_id,
                fill.agent_name,
                fill.broker_id,
                fill.symbol,
                fill.side,
                str(fill.expected_price),
                str(fill.actual_price),
                str(fill.quantity),
                fill.slippage_bps,
                fill.filled_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_fills_for_agent(
        self, agent_name: str, limit: int = 100
    ) -> list[dict]:
        """Return recent fills for an agent."""
        cursor = await self._db.execute(
            """
            SELECT * FROM execution_quality
            WHERE agent_name = ?
            ORDER BY filled_at DESC
            LIMIT ?
            """,
            (agent_name, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_all_fills(self, limit: int = 200) -> list[dict]:
        """Return recent fills across all agents."""
        cursor = await self._db.execute(
            """
            SELECT * FROM execution_quality
            ORDER BY filled_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_average_slippage(self, agent_name: str | None = None) -> dict:
        """Return average slippage stats, optionally filtered by agent."""
        if agent_name:
            cursor = await self._db.execute(
                """
                SELECT
                    agent_name,
                    COUNT(*) as fill_count,
                    AVG(slippage_bps) as avg_slippage_bps,
                    MAX(slippage_bps) as max_slippage_bps,
                    MIN(slippage_bps) as min_slippage_bps
                FROM execution_quality
                WHERE agent_name = ?
                GROUP BY agent_name
                """,
                (agent_name,),
            )
            row = await cursor.fetchone()
            if not row:
                return {"agent_name": agent_name, "fill_count": 0}
            return dict(row)
        else:
            cursor = await self._db.execute(
                """
                SELECT
                    agent_name,
                    COUNT(*) as fill_count,
                    AVG(slippage_bps) as avg_slippage_bps,
                    MAX(slippage_bps) as max_slippage_bps,
                    MIN(slippage_bps) as min_slippage_bps
                FROM execution_quality
                GROUP BY agent_name
                ORDER BY avg_slippage_bps DESC
                """
            )
            rows = await cursor.fetchall()
            return {"agents": [dict(r) for r in rows]}
