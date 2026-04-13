"""PortfolioStateStore — persists portfolio-level risk state across restarts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class PortfolioState:
    """Portfolio-level risk state."""

    high_water_mark: Decimal
    triggered: bool
    triggered_at: datetime | None
    updated_at: datetime


class PortfolioStateStore:
    """SQLite-backed storage for portfolio risk state.

    Persists high-water mark and kill switch trigger state to survive
    application restarts. Without this, the MaxDrawdownPct rule would
    lose its HWM on restart and fail to detect drawdowns correctly.
    """

    def __init__(self, db: "aiosqlite.Connection") -> None:
        self._db = db

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_state (
                key TEXT PRIMARY KEY,
                high_water_mark TEXT NOT NULL,
                triggered INTEGER NOT NULL DEFAULT 0,
                triggered_at TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_state_updated
            ON portfolio_state(updated_at DESC)
        """)
        await self._db.commit()

    async def get_state(self, key: str = "default") -> PortfolioState | None:
        """Get persisted portfolio state by key."""
        cursor = await self._db.execute(
            "SELECT * FROM portfolio_state WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        # Handle both dict and tuple row formats
        if isinstance(row, dict):
            return PortfolioState(
                high_water_mark=Decimal(row["high_water_mark"]),
                triggered=bool(row["triggered"]),
                triggered_at=(
                    datetime.fromisoformat(row["triggered_at"])
                    if row["triggered_at"]
                    else None
                ),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        else:
            _, hwm_str, triggered_int, triggered_at_str, updated_at_str = row
            return PortfolioState(
                high_water_mark=Decimal(hwm_str),
                triggered=bool(triggered_int),
                triggered_at=(
                    datetime.fromisoformat(triggered_at_str)
                    if triggered_at_str
                    else None
                ),
                updated_at=datetime.fromisoformat(updated_at_str),
            )

    async def save_state(self, state: PortfolioState, key: str = "default") -> None:
        """Persist portfolio state."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO portfolio_state (key, high_water_mark, triggered, triggered_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                high_water_mark = excluded.high_water_mark,
                triggered = excluded.triggered,
                triggered_at = excluded.triggered_at,
                updated_at = excluded.updated_at
            """,
            (
                key,
                str(state.high_water_mark),
                int(state.triggered),
                state.triggered_at.isoformat() if state.triggered_at else None,
                now,
            ),
        )
        await self._db.commit()

    async def update_hwm(self, hwm: Decimal, key: str = "default") -> None:
        """Update only the high-water mark."""
        state = await self.get_state(key)
        if state is None:
            state = PortfolioState(
                high_water_mark=hwm,
                triggered=False,
                triggered_at=None,
                updated_at=datetime.now(timezone.utc),
            )
        else:
            state.high_water_mark = hwm
            state.updated_at = datetime.now(timezone.utc)

        await self.save_state(state, key)

    async def set_triggered(self, triggered: bool, key: str = "default") -> None:
        """Set the triggered flag."""
        state = await self.get_state(key)
        now = datetime.now(timezone.utc)

        if state is None:
            state = PortfolioState(
                high_water_mark=Decimal("0"),
                triggered=triggered,
                triggered_at=now if triggered else None,
                updated_at=now,
            )
        else:
            state.triggered = triggered
            state.triggered_at = now if triggered else None
            state.updated_at = now

        await self.save_state(state, key)

    async def reset(self, key: str = "default") -> None:
        """Reset state to defaults."""
        state = PortfolioState(
            high_water_mark=Decimal("0"),
            triggered=False,
            triggered_at=None,
            updated_at=datetime.now(timezone.utc),
        )
        await self.save_state(state, key)
