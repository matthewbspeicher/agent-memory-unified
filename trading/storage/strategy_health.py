"""StrategyHealthStore — persists current strategy health state and audit events."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import aiosqlite

class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)



class StrategyHealthStore:
    """Persists strategy_health rows (one per agent) and strategy_health_events audit log."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Current-state reads
    # ------------------------------------------------------------------

    async def get_status(self, agent_name: str) -> dict[str, Any] | None:
        """Return current health row for agent, or None if no record exists."""
        cursor = await self._db.execute(
            "SELECT * FROM strategy_health WHERE agent_name = ?",
            (agent_name,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_statuses(self) -> list[dict[str, Any]]:
        """Return all agent health rows ordered by agent_name."""
        cursor = await self._db.execute(
            "SELECT * FROM strategy_health ORDER BY agent_name ASC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Current-state writes
    # ------------------------------------------------------------------

    async def upsert_status(
        self,
        agent_name: str,
        status: str,
        *,
        health_score: float | None = None,
        rolling_expectancy: str | None = None,
        rolling_net_pnl: str | None = None,
        rolling_drawdown: str | None = None,
        rolling_win_rate: float | None = None,
        rolling_trade_count: int = 0,
        throttle_multiplier: float | None = None,
        trigger_reason: str | None = None,
        cooldown_until: str | None = None,
        manual_override: str | None = None,
    ) -> None:
        """INSERT OR REPLACE the current health state row for agent_name."""
        updated_at = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO strategy_health (
                agent_name, status, health_score,
                rolling_expectancy, rolling_net_pnl, rolling_drawdown,
                rolling_win_rate, rolling_trade_count,
                throttle_multiplier, trigger_reason,
                cooldown_until, manual_override, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_name) DO UPDATE SET
                status = excluded.status,
                health_score = excluded.health_score,
                rolling_expectancy = excluded.rolling_expectancy,
                rolling_net_pnl = excluded.rolling_net_pnl,
                rolling_drawdown = excluded.rolling_drawdown,
                rolling_win_rate = excluded.rolling_win_rate,
                rolling_trade_count = excluded.rolling_trade_count,
                throttle_multiplier = excluded.throttle_multiplier,
                trigger_reason = excluded.trigger_reason,
                cooldown_until = excluded.cooldown_until,
                manual_override = excluded.manual_override,
                updated_at = excluded.updated_at
            """,
            (
                agent_name, status, health_score,
                rolling_expectancy, rolling_net_pnl, rolling_drawdown,
                rolling_win_rate, rolling_trade_count,
                throttle_multiplier, trigger_reason,
                cooldown_until, manual_override, updated_at,
            ),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Audit-event writes
    # ------------------------------------------------------------------

    async def record_event(
        self,
        agent_name: str,
        old_status: str | None,
        new_status: str,
        reason: str,
        metrics_snapshot: dict[str, Any],
        actor: str,
    ) -> None:
        """Append one audit-log row to strategy_health_events."""
        created_at = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO strategy_health_events
                (agent_name, old_status, new_status, reason, metrics_snapshot, created_at, actor)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_name,
                old_status,
                new_status,
                reason,
                json.dumps(metrics_snapshot, cls=_DecimalEncoder),
                created_at,
                actor,
            ),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Audit-event reads
    # ------------------------------------------------------------------

    async def get_events(
        self,
        agent_name: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent health events for an agent, newest first."""
        cursor = await self._db.execute(
            """
            SELECT * FROM strategy_health_events
            WHERE agent_name = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (agent_name, limit),
        )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            row_dict = dict(r)
            # Deserialize metrics_snapshot JSON
            try:
                row_dict["metrics_snapshot"] = json.loads(row_dict.get("metrics_snapshot") or "{}")
            except (json.JSONDecodeError, TypeError):
                row_dict["metrics_snapshot"] = {}
            result.append(row_dict)
        return result

    # ------------------------------------------------------------------
    # Manual override
    # ------------------------------------------------------------------

    async def set_override(
        self,
        agent_name: str,
        status: str,
        actor: str,
        reason: str = "manual override",
    ) -> None:
        """Apply a manual operator override: upsert new status + record audit event."""
        existing = await self.get_status(agent_name)
        old_status = existing["status"] if existing else None

        await self.upsert_status(
            agent_name,
            status,
            trigger_reason=reason,
            manual_override=actor,
        )
        await self.record_event(
            agent_name=agent_name,
            old_status=old_status,
            new_status=status,
            reason=reason,
            metrics_snapshot={},
            actor=actor,
        )
