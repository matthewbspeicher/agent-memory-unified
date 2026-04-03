import aiosqlite
from decimal import Decimal
from pydantic import BaseModel
from datetime import datetime, timezone

class PerformanceSnapshot(BaseModel):
    id: int | None = None
    agent_name: str
    timestamp: datetime
    opportunities_generated: int
    opportunities_executed: int
    win_rate: float
    total_pnl: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    daily_pnl_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    profit_factor: float = 0.0
    total_trades: int = 0
    open_positions: int = 0

class PerformanceStore:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def save(self, snapshot: PerformanceSnapshot) -> None:
        ts = snapshot.timestamp
        if not ts.tzinfo:
            ts = ts.replace(tzinfo=timezone.utc)

        await self._db.execute(
            """
            INSERT INTO performance_snapshots
            (agent_name, timestamp, opportunities_generated, opportunities_executed, win_rate,
             total_pnl, daily_pnl, daily_pnl_pct, sharpe_ratio, max_drawdown,
             avg_win, avg_loss, profit_factor, total_trades, open_positions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.agent_name,
                ts.isoformat(),
                snapshot.opportunities_generated,
                snapshot.opportunities_executed,
                snapshot.win_rate,
                str(snapshot.total_pnl),
                str(snapshot.daily_pnl),
                snapshot.daily_pnl_pct,
                snapshot.sharpe_ratio,
                snapshot.max_drawdown,
                str(snapshot.avg_win),
                str(snapshot.avg_loss),
                snapshot.profit_factor,
                snapshot.total_trades,
                snapshot.open_positions,
            )
        )
        await self._db.commit()

    async def get_history(self, agent_name: str, limit: int = 100) -> list[PerformanceSnapshot]:
        cursor = await self._db.execute(
            """
            SELECT id, agent_name, timestamp, opportunities_generated, opportunities_executed, win_rate,
                   total_pnl, daily_pnl, daily_pnl_pct, sharpe_ratio, max_drawdown,
                   avg_win, avg_loss, profit_factor, total_trades, open_positions
            FROM performance_snapshots
            WHERE agent_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (agent_name, limit)
        )
        rows = await cursor.fetchall()

        results = []
        for r in rows:
            results.append(PerformanceSnapshot(
                id=r["id"],
                agent_name=r["agent_name"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                opportunities_generated=r["opportunities_generated"],
                opportunities_executed=r["opportunities_executed"],
                win_rate=r["win_rate"],
                total_pnl=Decimal(r["total_pnl"] or "0"),
                daily_pnl=Decimal(r["daily_pnl"] or "0"),
                daily_pnl_pct=r["daily_pnl_pct"] or 0.0,
                sharpe_ratio=r["sharpe_ratio"] or 0.0,
                max_drawdown=r["max_drawdown"] or 0.0,
                avg_win=Decimal(r["avg_win"] or "0"),
                avg_loss=Decimal(r["avg_loss"] or "0"),
                profit_factor=r["profit_factor"] or 0.0,
                total_trades=r["total_trades"] or 0,
                open_positions=r["open_positions"] or 0,
            ))
        return results

    async def get_latest(self, agent_name: str) -> PerformanceSnapshot | None:
        results = await self.get_history(agent_name, limit=1)
        return results[0] if results else None

    async def seed_if_empty(self, agent_names: list[str]) -> int:
        """Insert a zero-state snapshot for agents that have no snapshots yet.

        Returns the number of agents seeded.
        """
        now = datetime.now(timezone.utc)
        seeded = 0
        for name in agent_names:
            existing = await self.get_latest(name)
            if existing is not None:
                continue
            await self.save(PerformanceSnapshot(
                agent_name=name,
                timestamp=now,
                opportunities_generated=0,
                opportunities_executed=0,
                win_rate=0.0,
            ))
            seeded += 1
        return seeded
