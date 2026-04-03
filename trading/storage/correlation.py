"""CorrelationStore — persists correlation snapshots and history."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from learning.correlation_monitor import (
    CorrelationAlertLevel,
    CorrelationPair,
    CorrelationSnapshot,
)

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)


class CorrelationStore:
    """SQLite-backed storage for correlation monitoring data."""

    def __init__(self, db: "aiosqlite.Connection") -> None:
        self._db = db

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS correlation_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                alert_level TEXT NOT NULL,
                portfolio_diversification_score REAL NOT NULL,
                agent_count INTEGER NOT NULL,
                analyzed_pairs INTEGER NOT NULL,
                skipped_pairs INTEGER NOT NULL,
                high_correlation_pairs_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_correlation_snapshots_timestamp
            ON correlation_snapshots(timestamp DESC)
        """)
        await self._db.commit()

    async def save_snapshot(self, snapshot: CorrelationSnapshot) -> None:
        """Persist a correlation snapshot."""
        pairs_json = json.dumps(
            [
                {
                    "agent_a": p.agent_a,
                    "agent_b": p.agent_b,
                    "correlation": p.correlation,
                    "sample_size": p.sample_size,
                    "lookback_days": p.lookback_days,
                }
                for p in snapshot.high_correlation_pairs
            ]
        )
        now = datetime.now(timezone.utc).isoformat()

        await self._db.execute(
            """
            INSERT INTO correlation_snapshots
            (timestamp, alert_level, portfolio_diversification_score,
             agent_count, analyzed_pairs, skipped_pairs,
             high_correlation_pairs_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.timestamp.isoformat(),
                snapshot.alert_level.value,
                snapshot.portfolio_diversification_score,
                snapshot.agent_count,
                snapshot.analyzed_pairs,
                snapshot.skipped_pairs,
                pairs_json,
                now,
            ),
        )
        await self._db.commit()

    async def get_latest_snapshot(self) -> CorrelationSnapshot | None:
        """Get the most recent correlation snapshot."""
        cursor = await self._db.execute(
            """
            SELECT timestamp, alert_level, portfolio_diversification_score,
                   agent_count, analyzed_pairs, skipped_pairs,
                   high_correlation_pairs_json
            FROM correlation_snapshots
            ORDER BY timestamp DESC
            LIMIT 1
            """
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        # Handle both dict and tuple row formats
        if isinstance(row, dict):
            timestamp_str = row["timestamp"]
            alert_level_str = row["alert_level"]
            portfolio_score = row["portfolio_diversification_score"]
            agent_count = row["agent_count"]
            analyzed_pairs = row["analyzed_pairs"]
            skipped_pairs = row["skipped_pairs"]
            pairs_json = row["high_correlation_pairs_json"]
        else:
            (
                timestamp_str,
                alert_level_str,
                portfolio_score,
                agent_count,
                analyzed_pairs,
                skipped_pairs,
                pairs_json,
            ) = row

        # Parse pairs
        pairs_data = json.loads(pairs_json) if pairs_json else []
        high_corr_pairs = [
            CorrelationPair(
                agent_a=p["agent_a"],
                agent_b=p["agent_b"],
                correlation=p["correlation"],
                sample_size=p["sample_size"],
                lookback_days=p["lookback_days"],
            )
            for p in pairs_data
        ]

        return CorrelationSnapshot(
            timestamp=datetime.fromisoformat(timestamp_str),
            alert_level=CorrelationAlertLevel(alert_level_str),
            portfolio_diversification_score=portfolio_score,
            high_correlation_pairs=high_corr_pairs,
            agent_count=agent_count,
            analyzed_pairs=analyzed_pairs,
            skipped_pairs=skipped_pairs,
        )

    async def get_snapshot_history(
        self,
        limit: int = 100,
        start_date: str | None = None,
    ) -> list[CorrelationSnapshot]:
        """Get historical correlation snapshots."""
        query = """
            SELECT timestamp, alert_level, portfolio_diversification_score,
                   agent_count, analyzed_pairs, skipped_pairs,
                   high_correlation_pairs_json
            FROM correlation_snapshots
        """
        params: list = []

        if start_date:
            query += " WHERE timestamp >= ?"
            params.append(start_date)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()

        snapshots: list[CorrelationSnapshot] = []
        for row in rows:
            if isinstance(row, dict):
                timestamp_str = row["timestamp"]
                alert_level_str = row["alert_level"]
                portfolio_score = row["portfolio_diversification_score"]
                agent_count = row["agent_count"]
                analyzed_pairs = row["analyzed_pairs"]
                skipped_pairs = row["skipped_pairs"]
                pairs_json = row["high_correlation_pairs_json"]
            else:
                (
                    timestamp_str,
                    alert_level_str,
                    portfolio_score,
                    agent_count,
                    analyzed_pairs,
                    skipped_pairs,
                    pairs_json,
                ) = row

            pairs_data = json.loads(pairs_json) if pairs_json else []
            high_corr_pairs = [
                CorrelationPair(
                    agent_a=p["agent_a"],
                    agent_b=p["agent_b"],
                    correlation=p["correlation"],
                    sample_size=p["sample_size"],
                    lookback_days=p["lookback_days"],
                )
                for p in pairs_data
            ]

            snapshots.append(
                CorrelationSnapshot(
                    timestamp=datetime.fromisoformat(timestamp_str),
                    alert_level=CorrelationAlertLevel(alert_level_str),
                    portfolio_diversification_score=portfolio_score,
                    high_correlation_pairs=high_corr_pairs,
                    agent_count=agent_count,
                    analyzed_pairs=analyzed_pairs,
                    skipped_pairs=skipped_pairs,
                )
            )

        return snapshots
