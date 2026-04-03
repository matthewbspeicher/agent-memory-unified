"""
LeaderboardEngine — on-demand agent ranking by Sharpe ratio with ELO.

Data sources (merged into AgentRanking):
  - PerformanceStore snapshots (local): sharpe_ratio, total_pnl, win_rate
  - Remembr.dev profiles (authoritative): elo, win_count, loss_count, streak

Orchestration flow:
  1. compute_rankings(profiles) — merge snapshot + remembr.dev state
  2. run_matches(rankings)      — round-robin pairwise (N>=2 required)
  3. tally_results(matches)     — accumulate win/loss/streak deltas
  4. update_elo(matches, elo)   — K_effective = 32 / (N-1)
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite
    from agents.runner import AgentRunner
    from storage.performance import PerformanceStore

logger = logging.getLogger(__name__)

DEFAULT_ELO = 1000
K_BASE = 32


@dataclass
class AgentRanking:
    agent_name: str
    # From PerformanceSnapshot (local):
    sharpe_ratio: float
    total_pnl: float
    win_rate: float
    # From remembr.dev profile (authoritative), defaults on cold start:
    elo: int = DEFAULT_ELO
    win_count: int = 0
    loss_count: int = 0
    streak: int = 0  # positive = consecutive wins, negative = losses


@dataclass
class MatchResult:
    winner: str
    loser: str
    winner_sharpe: float
    loser_sharpe: float


class LeaderboardEngine:
    def __init__(
        self,
        perf_store: PerformanceStore,
        runner: AgentRunner,
        db: aiosqlite.Connection,
        remembr_sync=None,
    ) -> None:
        self._perf_store = perf_store
        self._runner = runner
        self._db = db
        self._remembr_sync = remembr_sync
        self._cache: list[AgentRanking] | None = None

    async def compute_rankings(
        self, profiles: dict[str, AgentRanking] | None = None,
    ) -> list[AgentRanking]:
        """Build AgentRanking list by merging local snapshots with remembr.dev profiles."""
        agents = self._runner.list_agents()
        rankings: list[AgentRanking] = []

        for info in agents:
            snapshot = await self._perf_store.get_latest(info.name)
            if snapshot is None:
                continue

            # Merge with remembr.dev profile if available
            profile = profiles.get(info.name) if profiles else None
            rankings.append(AgentRanking(
                agent_name=info.name,
                sharpe_ratio=snapshot.sharpe_ratio,
                total_pnl=float(snapshot.total_pnl),
                win_rate=snapshot.win_rate,
                elo=profile.elo if profile else DEFAULT_ELO,
                win_count=profile.win_count if profile else 0,
                loss_count=profile.loss_count if profile else 0,
                streak=profile.streak if profile else 0,
            ))

        rankings.sort(key=lambda r: r.sharpe_ratio, reverse=True)
        return rankings

    def run_matches(self, rankings: list[AgentRanking]) -> list[MatchResult]:
        """Round-robin pairwise comparisons. Higher Sharpe wins. N>=2 required."""
        n = len(rankings)
        if n < 2:
            if n == 1:
                logger.info("Only 1 agent — skipping matches, ELO unchanged")
            return []

        matches: list[MatchResult] = []
        for i in range(n):
            for j in range(i + 1, n):
                a, b = rankings[i], rankings[j]
                if a.sharpe_ratio > b.sharpe_ratio:
                    matches.append(MatchResult(a.agent_name, b.agent_name, a.sharpe_ratio, b.sharpe_ratio))
                elif b.sharpe_ratio > a.sharpe_ratio:
                    matches.append(MatchResult(b.agent_name, a.agent_name, b.sharpe_ratio, a.sharpe_ratio))
                # Equal Sharpe → no match (tie = no result)
        return matches

    def tally_results(
        self, matches: list[MatchResult], rankings: list[AgentRanking],
    ) -> list[AgentRanking]:
        """Accumulate win/loss deltas and update streaks from match results."""
        wins: dict[str, int] = {}
        losses: dict[str, int] = {}
        for m in matches:
            wins[m.winner] = wins.get(m.winner, 0) + 1
            losses[m.loser] = losses.get(m.loser, 0) + 1

        for r in rankings:
            w = wins.get(r.agent_name, 0)
            l = losses.get(r.agent_name, 0)
            r.win_count += w
            r.loss_count += l
            # Update streak
            if w > 0 and l == 0:
                r.streak = abs(r.streak) + w if r.streak >= 0 else w
            elif l > 0 and w == 0:
                r.streak = -(abs(r.streak) + l) if r.streak <= 0 else -l
            else:
                r.streak = 0  # mixed results reset streak

        return rankings

    def update_elo(
        self, matches: list[MatchResult], current_elo: dict[str, int],
    ) -> dict[str, int]:
        """ELO with K_effective = 32 / (N-1) to bound total swing."""
        if not matches:
            return dict(current_elo)

        agents = set()
        for m in matches:
            agents.add(m.winner)
            agents.add(m.loser)
        n = len(agents)
        k = K_BASE / max(n - 1, 1)

        elo = dict(current_elo)
        for m in matches:
            ra = elo.get(m.winner, DEFAULT_ELO)
            rb = elo.get(m.loser, DEFAULT_ELO)
            ea = 1 / (1 + math.pow(10, (rb - ra) / 400))
            eb = 1 - ea
            elo[m.winner] = round(ra + k * (1 - ea))
            elo[m.loser] = max(1, round(rb + k * (0 - eb)))  # floor at 1

        return elo

    async def get_cached_leaderboard(self) -> list[AgentRanking] | None:
        """Return cached leaderboard from SQLite, or None if empty."""
        try:
            cursor = await self._db.execute(
                "SELECT rankings_json, last_processed_snapshot_at, updated_at, source "
                "FROM leaderboard_cache WHERE id = 1"
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            data = json.loads(row["rankings_json"] if isinstance(row, dict) else row[0])
            return [AgentRanking(**r) for r in data]
        except Exception as exc:
            logger.warning("Failed to read leaderboard cache: %s", exc)
            return None

    async def save_cache(
        self, rankings: list[AgentRanking], snapshot_ts: str, source: str = "live",
    ) -> None:
        """Persist leaderboard to SQLite singleton row."""
        rankings_json = json.dumps([asdict(r) for r in rankings])
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT OR REPLACE INTO leaderboard_cache
               (id, rankings_json, last_processed_snapshot_at, updated_at, source)
               VALUES (1, ?, ?, ?, ?)""",
            (rankings_json, snapshot_ts, now, source),
        )
        await self._db.commit()

    async def get_latest_snapshot_ts(self) -> str | None:
        """Get the most recent snapshot timestamp across all agents."""
        agents = self._runner.list_agents()
        latest: datetime | None = None
        for info in agents:
            snap = await self._perf_store.get_latest(info.name)
            if snap and (latest is None or snap.timestamp > latest):
                latest = snap.timestamp
        return latest.isoformat() if latest else None

    async def is_stale(self) -> bool:
        """Check if new snapshots exist since last cached run."""
        latest_ts = await self.get_latest_snapshot_ts()
        if latest_ts is None:
            return False
        try:
            cursor = await self._db.execute(
                "SELECT last_processed_snapshot_at FROM leaderboard_cache WHERE id = 1"
            )
            row = await cursor.fetchone()
            if row is None:
                return True
            cached_ts = row["last_processed_snapshot_at"] if isinstance(row, dict) else row[0]
            return latest_ts != cached_ts
        except Exception:
            return True
