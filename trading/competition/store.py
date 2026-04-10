# trading/competition/store.py

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from competition.models import (
    AgentCard,
    AgentTrait,
    CardRarity,
    CardStats,
    CompetitorCreate,
    CompetitorRecord,
    CompetitorType,
    CompetitorXP,
    EloRating,
    LeaderboardEntry,
    MissionId,
    MissionProgress,
    MissionResponse,
    MissionType,
    Season,
    SeasonLeaderboard,
    SeasonLeaderboardEntry,
    SeasonStatus,
    Tier,
    TraitLoadout,
    TraitUnlock,
    XpHistoryEntry,
    XpSource,
    CARD_RARITY_THRESHOLDS,
    ELO_SOFT_RESET_TARGET,
    MISSION_INFO,
    SEASON_DURATION_DAYS,
    TRAIT_REQUIREMENTS,
    card_rarity_for_achievements,
    level_from_xp,
    tier_for_elo,
)

logger = logging.getLogger(__name__)


class CompetitionStore:
    """Persistence layer for the Arena Alpha competition system."""

    def __init__(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Competitors
    # ------------------------------------------------------------------

    async def upsert_competitor(self, competitor: CompetitorCreate) -> str:
        """Insert or update a competitor.  Returns the competitor id."""
        raw_id = f"{competitor.type.value}:{competitor.ref_id}"
        comp_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_id))
        sql = """
            INSERT INTO competitors (id, type, name, ref_id, metadata)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (type, ref_id) DO UPDATE
                SET name = EXCLUDED.name,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """
        params = [
            comp_id,
            competitor.type.value,
            competitor.name,
            competitor.ref_id,
            json.dumps(competitor.metadata),
        ]
        async with self._db.execute(sql, params) as cur:
            row = await cur.fetchone()
        return str(row["id"]) if row else ""

    async def get_competitor(self, competitor_id: str) -> CompetitorRecord | None:
        """Look up a competitor by primary key."""
        sql = "SELECT * FROM competitors WHERE id = ?"
        async with self._db.execute(sql, [competitor_id]) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _row_to_competitor(row)

    async def get_competitor_by_ref(
        self, comp_type: CompetitorType, ref_id: str
    ) -> CompetitorRecord | None:
        """Look up a competitor by (type, ref_id) unique key."""
        sql = "SELECT * FROM competitors WHERE type = ? AND ref_id = ?"
        async with self._db.execute(sql, [comp_type.value, ref_id]) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _row_to_competitor(row)

    async def list_competitors(
        self, comp_type: CompetitorType | None = None
    ) -> list[CompetitorRecord]:
        """List active competitors, optionally filtered by type."""
        if comp_type is not None:
            sql = "SELECT * FROM competitors WHERE status = 'active' AND type = ? ORDER BY name"
            params: list[Any] = [comp_type.value]
        else:
            sql = "SELECT * FROM competitors WHERE status = 'active' ORDER BY name"
            params = []
        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [_row_to_competitor(r) for r in rows]

    # ------------------------------------------------------------------
    # ELO Ratings
    # ------------------------------------------------------------------

    async def ensure_elo_rating(self, competitor_id: str, asset: str) -> None:
        """Create an ELO rating row if it does not exist."""
        elo_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{competitor_id}:{asset}"))
        sql = """
            INSERT INTO elo_ratings (id, competitor_id, asset)
            VALUES (?, ?, ?)
            ON CONFLICT (competitor_id, asset) DO NOTHING
        """
        await self._db.execute(sql, [elo_id, competitor_id, asset])

    async def get_elo(self, competitor_id: str, asset: str) -> int:
        """Return the current ELO for a competitor+asset (default 1000)."""
        sql = "SELECT elo FROM elo_ratings WHERE competitor_id = ? AND asset = ?"
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            row = await cur.fetchone()
        return row["elo"] if row else 1000

    async def update_elo(
        self,
        competitor_id: str,
        asset: str,
        new_elo: int,
        elo_delta: int,
    ) -> None:
        """Update the live ELO rating and append a history record."""
        tier = tier_for_elo(new_elo)
        update_sql = """
            UPDATE elo_ratings
            SET elo = ?, tier = ?, matches_count = matches_count + 1, updated_at = CURRENT_TIMESTAMP
            WHERE competitor_id = ? AND asset = ?
        """
        await self._db.execute(update_sql, [new_elo, tier.value, competitor_id, asset])

        elo_hist_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_DNS, f"{competitor_id}:{asset}:{new_elo}:{elo_delta}"
            )
        )
        history_sql = """
            INSERT INTO elo_history (id, competitor_id, asset, elo, tier, elo_delta)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        await self._db.execute(
            history_sql,
            [elo_hist_id, competitor_id, asset, new_elo, tier.value, elo_delta],
        )

    async def get_elo_history(
        self, competitor_id: str, asset: str, days: int = 30
    ) -> list[dict]:
        """Return recent ELO history entries."""
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        sql = """
            SELECT elo, tier, elo_delta, recorded_at
            FROM elo_history
            WHERE competitor_id = ?
              AND asset = ?
              AND recorded_at >= ?
            ORDER BY recorded_at DESC
        """
        async with self._db.execute(sql, [competitor_id, asset, cutoff]) as cur:
            rows = await cur.fetchall()
        return rows

    # ------------------------------------------------------------------
    # XP & Level
    # ------------------------------------------------------------------

    async def get_xp(self, competitor_id: str, asset: str) -> CompetitorXP:
        """Get XP and level data for a competitor on an asset."""
        from competition.models import level_from_xp, xp_to_next_level

        sql = "SELECT xp FROM elo_ratings WHERE competitor_id = ? AND asset = ?"
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            row = await cur.fetchone()
        xp_val = row["xp"] if row else 0
        return CompetitorXP.from_xp(competitor_id, asset, xp_val)

    async def award_xp(
        self,
        competitor_id: str,
        asset: str,
        source: XpSource,
        amount: int | None = None,
    ) -> CompetitorXP:
        """Award XP to a competitor and record the history.

        If amount is None, uses the default from XP_AMOUNTS.
        Returns the updated CompetitorXP state.
        """
        from competition.models import XP_AMOUNTS, level_from_xp, xp_to_next_level

        xp_amount = amount if amount is not None else XP_AMOUNTS[source]

        update_sql = """
            UPDATE elo_ratings
            SET xp = COALESCE(xp, 0) + ?, updated_at = CURRENT_TIMESTAMP
            WHERE competitor_id = ? AND asset = ?
            RETURNING xp
        """
        async with self._db.execute(
            update_sql, [xp_amount, competitor_id, asset]
        ) as cur:
            row = await cur.fetchone()
        new_xp = row["xp"] if row else xp_amount

        hist_id = str(uuid.uuid4())
        history_sql = """
            INSERT INTO xp_history (id, competitor_id, asset, source, amount)
            VALUES (?, ?, ?, ?, ?)
        """
        await self._db.execute(
            history_sql, [hist_id, competitor_id, asset, source.value, xp_amount]
        )

        return CompetitorXP.from_xp(competitor_id, asset, new_xp)

    async def get_xp_history(
        self, competitor_id: str, asset: str, limit: int = 50
    ) -> list[XpHistoryEntry]:
        """Get recent XP award history for a competitor."""
        sql = """
            SELECT id, competitor_id, asset, source, amount, created_at
            FROM xp_history
            WHERE competitor_id = ? AND asset = ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        async with self._db.execute(sql, [competitor_id, asset, limit]) as cur:
            rows = await cur.fetchall()
        return [
            XpHistoryEntry(
                id=str(r["id"]),
                competitor_id=str(r["competitor_id"]),
                asset=r["asset"],
                source=XpSource(r["source"]),
                amount=r["amount"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Traits
    # ------------------------------------------------------------------

    async def get_unlocked_traits(self, competitor_id: str) -> list[AgentTrait]:
        """Get all traits unlocked by a competitor."""
        sql = """
            SELECT trait FROM unlocked_traits
            WHERE competitor_id = ?
            ORDER BY unlocked_at ASC
        """
        async with self._db.execute(sql, [competitor_id]) as cur:
            rows = await cur.fetchall()
        return [AgentTrait(r["trait"]) for r in rows]

    async def unlock_trait(
        self, competitor_id: str, trait: AgentTrait, level: int
    ) -> TraitUnlock | None:
        """Unlock a trait for a competitor if they meet the level requirement.

        Returns the TraitUnlock record, or None if already unlocked / level too low.
        """
        # Check level requirement
        required = TRAIT_REQUIREMENTS.get(trait, 0)
        if level < required:
            return None

        # Check if already unlocked
        existing = await self.get_unlocked_traits(competitor_id)
        if trait in existing:
            return None

        # Insert the unlock
        unlock_id = str(uuid.uuid4())
        sql = """
            INSERT INTO unlocked_traits (id, competitor_id, trait, unlocked_at_level)
            VALUES (?, ?, ?, ?)
            RETURNING id, unlocked_at
        """
        async with self._db.execute(
            sql, [unlock_id, competitor_id, trait.value, level]
        ) as cur:
            row = await cur.fetchone()

        if not row:
            return None

        return TraitUnlock(
            id=str(row["id"]),
            competitor_id=competitor_id,
            trait=trait,
            unlocked_at=row["unlocked_at"],
            unlocked_at_level=level,
        )

    async def auto_unlock_traits(
        self, competitor_id: str, level: int
    ) -> list[AgentTrait]:
        """Auto-unlock any traits the competitor is now eligible for.

        Called after level up. Returns list of newly unlocked traits.
        """
        already_unlocked = await self.get_unlocked_traits(competitor_id)
        newly_unlocked = []

        for trait, required_level in TRAIT_REQUIREMENTS.items():
            if trait in already_unlocked:
                continue
            if level >= required_level:
                result = await self.unlock_trait(competitor_id, trait, level)
                if result:
                    newly_unlocked.append(trait)

        return newly_unlocked

    async def get_loadout(self, competitor_id: str, asset: str) -> TraitLoadout:
        """Get the current trait loadout for a competitor on an asset."""
        sql = """
            SELECT primary_trait, secondary_trait, tertiary_trait
            FROM trait_loadout
            WHERE competitor_id = ? AND asset = ?
        """
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            row = await cur.fetchone()

        if not row:
            return TraitLoadout(
                competitor_id=competitor_id,
                asset=asset,
                primary=AgentTrait.GENESIS,
            )

        return TraitLoadout(
            competitor_id=competitor_id,
            asset=asset,
            primary=AgentTrait(row["primary_trait"]) if row["primary_trait"] else None,
            secondary=AgentTrait(row["secondary_trait"])
            if row["secondary_trait"]
            else None,
            tertiary=AgentTrait(row["tertiary_trait"])
            if row["tertiary_trait"]
            else None,
        )

    async def update_loadout(self, loadout: TraitLoadout) -> TraitLoadout:
        """Upsert the trait loadout for a competitor on an asset."""
        sql = """
            INSERT INTO trait_loadout (id, competitor_id, asset, primary_trait, secondary_trait, tertiary_trait)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (competitor_id, asset) DO UPDATE
                SET primary_trait = EXCLUDED.primary_trait,
                    secondary_trait = EXCLUDED.secondary_trait,
                    tertiary_trait = EXCLUDED.tertiary_trait,
                    updated_at = CURRENT_TIMESTAMP
        """
        loadout_id = str(
            uuid.uuid5(uuid.NAMESPACE_DNS, f"{loadout.competitor_id}:{loadout.asset}")
        )
        await self._db.execute(
            sql,
            [
                loadout_id,
                loadout.competitor_id,
                loadout.asset,
                loadout.primary.value if loadout.primary else None,
                loadout.secondary.value if loadout.secondary else None,
                loadout.tertiary.value if loadout.tertiary else None,
            ],
        )
        return loadout

    async def equip_trait(
        self, competitor_id: str, asset: str, trait: AgentTrait
    ) -> TraitLoadout | None:
        """Equip a trait in the first empty slot. Returns None if trait not unlocked."""
        # Verify trait is unlocked
        unlocked = await self.get_unlocked_traits(competitor_id)
        if trait not in unlocked:
            return None

        loadout = await self.get_loadout(competitor_id, asset)
        if not loadout.equip(trait):
            return None  # Loadout full

        return await self.update_loadout(loadout)

    async def unequip_trait(
        self, competitor_id: str, asset: str, trait: AgentTrait
    ) -> TraitLoadout:
        """Remove a trait from the loadout."""
        loadout = await self.get_loadout(competitor_id, asset)
        loadout.unequip(trait)
        return await self.update_loadout(loadout)

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------

    async def get_leaderboard(
        self,
        asset: str,
        comp_type: CompetitorType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LeaderboardEntry]:
        """Fetch the leaderboard for a given asset, ordered by ELO desc."""
        if comp_type is not None:
            sql = """
                SELECT c.id, c.type, c.name, c.ref_id, c.status,
                       e.elo, e.tier, e.matches_count,
                       COALESCE(e.xp, 0) AS xp,
                       COALESCE(s.current_count, 0) AS current_streak,
                       COALESCE(s.best_count, 0) AS best_streak
                FROM competitors c
                JOIN elo_ratings e ON e.competitor_id = c.id AND e.asset = ?
                LEFT JOIN streaks s ON s.competitor_id = c.id
                    AND s.asset = ? AND s.streak_type = 'win'
                WHERE c.status = 'active' AND c.type = ?
                ORDER BY e.elo DESC
                LIMIT ? OFFSET ?
            """
            params: list[Any] = [asset, comp_type.value, limit, offset]
        else:
            sql = """
                SELECT c.id, c.type, c.name, c.ref_id, c.status,
                       e.elo, e.tier, e.matches_count,
                       COALESCE(e.xp, 0) AS xp,
                       COALESCE(s.current_count, 0) AS current_streak,
                       COALESCE(s.best_count, 0) AS best_streak
                FROM competitors c
                JOIN elo_ratings e ON e.competitor_id = c.id AND e.asset = ?
                LEFT JOIN streaks s ON s.competitor_id = c.id
                    AND s.asset = ? AND s.streak_type = 'win'
                WHERE c.status = 'active'
                ORDER BY e.elo DESC
                LIMIT ? OFFSET ?
            """
            params = [asset, asset, limit, offset]

        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [LeaderboardEntry.from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Dashboard summary
    # ------------------------------------------------------------------

    async def get_dashboard_summary(self, asset: str) -> dict:
        """Return a summary dict suitable for the frontend dashboard."""
        entries = await self.get_leaderboard(asset=asset)
        return {
            "asset": asset,
            "total_competitors": len(entries),
            "leaderboard": [e.model_dump() for e in entries],
        }

    async def get_recent_achievements(
        self, since_id: int = 0, limit: int = 10
    ) -> list[dict]:
        """Get recent achievements for SSE feed."""
        sql = """
            SELECT a.id, a.competitor_id, a.achievement_type, a.earned_at,
                   c.name, c.type
            FROM achievements a
            JOIN competitors c ON c.id = a.competitor_id
            WHERE a.id > ?
            ORDER BY a.earned_at ASC
            LIMIT ?
        """
        async with self._db.execute(sql, [since_id, limit]) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": row["id"],
                "competitor": row["name"],
                "competitor_type": row["type"],
                "type": row["achievement_type"],
                "earned_at": str(row["earned_at"]),
            }
            for row in rows
        ]

    async def get_competitor_calibration(
        self, competitor_id: str, asset: str = "BTC"
    ) -> float:
        """Get calibration score for a competitor (0.0-1.0)."""
        sql = """
            SELECT calibration_score
            FROM elo_ratings
            WHERE competitor_id = ? AND asset = ?
        """
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            row = await cur.fetchone()
        if row:
            return float(row.get("calibration_score", 0.85))
        return 0.85  # Default

    async def get_head_to_head(
        self, competitor_a: str, competitor_b: str, asset: str = "BTC"
    ) -> dict:
        """Return head-to-head win/loss/draw stats between two competitors."""
        sql = """
            SELECT
                COUNT(*) FILTER (WHERE winner_id = ?) AS wins_a,
                COUNT(*) FILTER (WHERE winner_id = ?) AS wins_b,
                COUNT(*) FILTER (WHERE winner_id IS NULL) AS draws,
                COUNT(*) AS total
            FROM matches
            WHERE ((competitor_a_id = ? AND competitor_b_id = ?)
                OR (competitor_a_id = ? AND competitor_b_id = ?))
                AND asset = ?
                AND match_type = 'pairwise'
        """
        async with self._db.execute(sql, [competitor_a, competitor_b, asset]) as cur:
            row = await cur.fetchone()
        return row or {"wins_a": 0, "wins_b": 0, "draws": 0, "total": 0}

    async def record_match(self, match_data: dict) -> None:
        """Record a match result in the matches table."""
        sql = """
            INSERT INTO matches (
                competitor_a_id, competitor_b_id, asset, time_window,
                winner_id, score_a, score_b, elo_delta_a, elo_delta_b, match_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        await self._db.execute(
            sql,
            [
                match_data.get("competitor_a_id"),
                match_data.get("competitor_b_id"),
                match_data.get("asset", "BTC"),
                match_data.get("window", "5m"),
                match_data.get("winner_id"),
                match_data.get("score_a", 0),
                match_data.get("score_b", 0),
                match_data.get("elo_delta_a", 0),
                match_data.get("elo_delta_b", 0),
                match_data.get("match_type", "baseline"),
            ],
        )

    # ------------------------------------------------------------------
    # Trait System
    # ------------------------------------------------------------------

    async def get_unlocked_traits(self, competitor_id: str) -> list[dict]:
        """Get all unlocked traits for a competitor."""
        sql = """
            SELECT trait, unlocked_at, unlocked_at_level
            FROM unlocked_traits
            WHERE competitor_id = ?
            ORDER BY unlocked_at_level ASC
        """
        async with self._db.execute(sql, [competitor_id]) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def unlock_trait(
        self, competitor_id: str, trait: AgentTrait, level: int
    ) -> bool:
        """Unlock a trait for a competitor. Returns True if newly unlocked."""
        sql = """
            INSERT INTO unlocked_traits (competitor_id, trait, unlocked_at_level)
            VALUES (?, ?, ?)
            ON CONFLICT (competitor_id, trait) DO NOTHING
            RETURNING id
        """
        async with self._db.execute(sql, [competitor_id, trait.value, level]) as cur:
            row = await cur.fetchone()
        return row is not None

    async def auto_unlock_traits(
        self, competitor_id: str, current_level: int
    ) -> list[AgentTrait]:
        """Auto-unlock traits that the competitor is now eligible for.
        Returns list of newly unlocked traits.
        """
        newly_unlocked = []
        for trait, required_level in TRAIT_REQUIREMENTS.items():
            if current_level >= required_level:
                is_new = await self.unlock_trait(competitor_id, trait, current_level)
                if is_new:
                    newly_unlocked.append(trait)
        return newly_unlocked

    async def get_loadout(
        self, competitor_id: str, asset: str = "BTC"
    ) -> TraitLoadout | None:
        """Get the current trait loadout for a competitor."""
        sql = """
            SELECT primary_trait, secondary_trait, tertiary_trait
            FROM trait_loadout
            WHERE competitor_id = ? AND asset = ?
        """
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            row = await cur.fetchone()
        if not row:
            return TraitLoadout(competitor_id=competitor_id, asset=asset)
        return TraitLoadout(
            competitor_id=competitor_id,
            asset=asset,
            primary=AgentTrait(row["primary_trait"]) if row["primary_trait"] else None,
            secondary=AgentTrait(row["secondary_trait"])
            if row["secondary_trait"]
            else None,
            tertiary=AgentTrait(row["tertiary_trait"])
            if row["tertiary_trait"]
            else None,
        )

    async def equip_trait(
        self, competitor_id: str, trait: AgentTrait, asset: str = "BTC"
    ) -> TraitLoadout:
        """Equip a trait in the first empty slot."""
        loadout = await self.get_loadout(competitor_id, asset)
        if not loadout.equip(trait):
            raise ValueError("Loadout full - unequip a trait first")
        await self._save_loadout(loadout)
        return loadout

    async def unequip_trait(
        self, competitor_id: str, trait: AgentTrait, asset: str = "BTC"
    ) -> TraitLoadout:
        """Remove a trait from the loadout."""
        loadout = await self.get_loadout(competitor_id, asset)
        loadout.unequip(trait)
        await self._save_loadout(loadout)
        return loadout

    async def _save_loadout(self, loadout: TraitLoadout) -> None:
        """Save loadout to database."""
        sql = """
            INSERT INTO trait_loadout (competitor_id, asset, primary_trait, secondary_trait, tertiary_trait)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (competitor_id, asset) DO UPDATE
                SET primary_trait = EXCLUDED.primary_trait,
                    secondary_trait = EXCLUDED.secondary_trait,
                    tertiary_trait = EXCLUDED.tertiary_trait
        """
        await self._db.execute(
            sql,
            [
                loadout.competitor_id,
                loadout.asset,
                loadout.primary.value if loadout.primary else None,
                loadout.secondary.value if loadout.secondary else None,
                loadout.tertiary.value if loadout.tertiary else None,
            ],
        )

    # ------------------------------------------------------------------
    # Agent Card
    # ------------------------------------------------------------------

    async def generate_agent_card(
        self, competitor_id: str, asset: str = "BTC"
    ) -> AgentCard | None:
        """Generate a visual agent card with all stats and rarity."""
        # Get competitor info
        competitor = await self.get_competitor(competitor_id)
        if not competitor:
            return None

        # Get ELO/rating info
        sql = """
            SELECT elo, tier, matches_count, xp
            FROM elo_ratings
            WHERE competitor_id = ? AND asset = ?
        """
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            rating_row = await cur.fetchone()

        if not rating_row:
            return None

        elo = rating_row["elo"]
        tier = Tier(rating_row["tier"])
        matches_count = rating_row["matches_count"]
        xp = rating_row["xp"] or 0

        # Get achievement count
        sql = "SELECT COUNT(*) as count FROM achievements WHERE competitor_id = ?"
        async with self._db.execute(sql, [competitor_id]) as cur:
            ach_row = await cur.fetchone()
        achievement_count = ach_row["count"] if ach_row else 0

        # Get win count
        sql = """
            SELECT COUNT(*) as wins FROM matches
            WHERE winner_id = ? AND asset = ?
        """
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            win_row = await cur.fetchone()
        wins = win_row["wins"] if win_row else 0
        losses = matches_count - wins

        # Get best streak
        sql = """
            SELECT best_streak FROM streaks
            WHERE competitor_id = ? AND asset = ?
        """
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            streak_row = await cur.fetchone()
        best_streak = streak_row["best_streak"] if streak_row else 0

        # Get unlocked traits count
        unlocked_traits = await self.get_unlocked_traits(competitor_id)

        # Get calibration score
        calibration = await self.get_calibration_score(competitor_id, asset)

        # Calculate rarity and stats
        rarity = card_rarity_for_achievements(achievement_count)
        level = level_from_xp(xp)
        win_rate = (wins / matches_count * 100) if matches_count > 0 else 0.0

        stats = CardStats(
            matches=matches_count,
            wins=wins,
            losses=losses,
            win_rate=round(win_rate, 1),
            best_streak=best_streak,
            total_xp=xp,
            achievement_count=achievement_count,
            traits_unlocked=len(unlocked_traits),
            calibration_score=calibration,
        )

        # Get trait icons
        trait_icons = [TRAIT_REQUIREMENTS.get(t["trait"], "") for t in unlocked_traits]

        # Get top 5 achievement badges
        sql = """
            SELECT a.achievement_type, a.name, a.tier
            FROM achievements a
            WHERE a.competitor_id = ?
            ORDER BY a.earned_at DESC
            LIMIT 5
        """
        async with self._db.execute(sql, [competitor_id]) as cur:
            ach_rows = await cur.fetchall()
        achievement_badges = [
            {"type": str(r["achievement_type"]), "name": r["name"], "tier": r["tier"]}
            for r in ach_rows
        ]

        return AgentCard(
            competitor_id=competitor_id,
            name=competitor.name,
            level=level,
            tier=tier,
            elo=elo,
            rarity=rarity,
            stats=stats,
            trait_icons=trait_icons,
            achievement_badges=achievement_badges,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _row_to_competitor(row: dict) -> CompetitorRecord:
    meta = row.get("metadata", {})
    if isinstance(meta, str):
        meta = json.loads(meta)
    return CompetitorRecord(
        id=str(row["id"]),
        type=CompetitorType(row["type"]),
        name=row["name"],
        ref_id=row["ref_id"],
        status=row.get("status", "active"),
        metadata=meta,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )

    async def get_missions(
        self, competitor_id: str, mission_type: MissionType | None = None
    ) -> list[MissionResponse]:
        results = []
        for mission_id, info in MISSION_INFO.items():
            if mission_type and info["type"] != mission_type:
                continue

            async with self._db.execute(
                """
                SELECT * FROM mission_progress
                WHERE competitor_id = ? AND mission_id = ?
                ORDER BY period_start DESC LIMIT 1
                """,
                [competitor_id, mission_id.value],
            ) as cur:
                row = await cur.fetchone()

            if row:
                progress = MissionProgress(
                    id=str(row["id"]),
                    competitor_id=str(row["competitor_id"]),
                    mission_id=MissionId(row["mission_id"]),
                    progress=row["progress"],
                    target=row["target"],
                    completed=row["completed"],
                    claimed=row["claimed"],
                    xp_awarded=row["xp_awarded"],
                    period_start=row["period_start"],
                    period_end=row["period_end"],
                    updated_at=row.get("updated_at"),
                )
            else:
                progress = MissionProgress(
                    id="",
                    competitor_id=competitor_id,
                    mission_id=mission_id,
                    progress=0,
                    target=info["target"],
                    completed=False,
                    claimed=False,
                    xp_awarded=0,
                    period_start=datetime.utcnow(),
                    period_end=datetime.utcnow(),
                )

            results.append(
                MissionResponse(
                    id=progress.id,
                    mission_id=mission_id,
                    name=info["name"],
                    description=info["description"],
                    icon=info["icon"],
                    mission_type=info["type"],
                    progress=progress.progress,
                    target=progress.target,
                    progress_pct=progress.progress_pct,
                    completed=progress.completed,
                    claimed=progress.claimed,
                    xp_reward=info["xp_reward"],
                    is_claimable=progress.is_claimable,
                    period_end=progress.period_end,
                )
            )

        return results

    async def update_mission_progress(
        self,
        competitor_id: str,
        mission_id: MissionId,
        increment: int = 1,
    ) -> MissionProgress:
        info = MISSION_INFO[mission_id]
        now = datetime.utcnow()

        if info["type"] == MissionType.DAILY:
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=1)
        else:
            period_start = now - timedelta(days=now.weekday())
            period_start = period_start.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            period_end = period_start + timedelta(days=7)

        async with self._db.execute(
            """
            INSERT INTO mission_progress (
                id, competitor_id, mission_id, progress, target,
                completed, claimed, xp_awarded, period_start, period_end, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (competitor_id, mission_id, period_start)
            DO UPDATE SET
                progress = LEAST(mission_progress.progress + excluded.progress, mission_progress.target),
                completed = CASE
                    WHEN mission_progress.progress + excluded.progress >= mission_progress.target THEN TRUE
                    ELSE mission_progress.completed
                END,
                updated_at = excluded.updated_at
            RETURNING *
            """,
            [
                str(uuid.uuid4()),
                competitor_id,
                mission_id.value,
                increment,
                info["target"],
                False,
                False,
                0,
                period_start,
                period_end,
                now,
            ],
        ) as cur:
            row = await cur.fetchone()

        return MissionProgress(
            id=str(row["id"]),
            competitor_id=str(row["competitor_id"]),
            mission_id=MissionId(row["mission_id"]),
            progress=row["progress"],
            target=row["target"],
            completed=row["completed"],
            claimed=row["claimed"],
            xp_awarded=row["xp_awarded"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            updated_at=row.get("updated_at"),
        )

    async def claim_mission_reward(
        self, competitor_id: str, mission_id: MissionId, asset: str = "BTC"
    ) -> tuple[bool, int]:
        info = MISSION_INFO[mission_id]

        async with self._db.execute(
            """
            UPDATE mission_progress
            SET claimed = TRUE, xp_awarded = ?, updated_at = ?
            WHERE competitor_id = ? AND mission_id = ?
                AND completed = TRUE AND claimed = FALSE
            RETURNING *
            """,
            [info["xp_reward"], datetime.utcnow(), competitor_id, mission_id.value],
        ) as cur:
            row = await cur.fetchone()

        if not row:
            return False, 0

        await self.award_xp(
            competitor_id,
            asset,
            info["xp_reward"],
            XpSource.MISSION_COMPLETE,
        )

        return True, info["xp_reward"]

    async def get_seasons(
        self, competitor_id: str | None = None
    ) -> tuple[Season | None, list[Season]]:
        now = datetime.utcnow()
        async with self._db.execute("SELECT * FROM seasons ORDER BY number DESC LIMIT 10") as cur:
            rows = await cur.fetchall()

        seasons = []
        current = None

        for row in rows:
            started = row["started_at"]
            ends = row["ends_at"]
            days_remaining = max(0, (ends - now).days)

            if ends < now:
                status = SeasonStatus.ENDED
            elif started <= now:
                status = SeasonStatus.ACTIVE
            else:
                status = SeasonStatus.UPCOMING

            season = Season(
                id=str(row["id"]),
                number=row["number"],
                name=row["name"],
                status=status,
                started_at=started,
                ends_at=ends,
                days_remaining=days_remaining,
                total_participants=row.get("total_participants", 0),
            )

            if status == SeasonStatus.ACTIVE:
                current = season

            seasons.append(season)

        return current, seasons

    async def get_season_leaderboard(
        self, season_id: str, limit: int = 50
    ) -> SeasonLeaderboard:
        async with self._db.execute(
            """
            SELECT
                ROW_NUMBER() OVER (ORDER BY elo DESC) as rank,
                c.id, c.name, e.elo, e.tier, e.matches_count
            FROM elo_ratings e
            JOIN competitors c ON c.id = e.competitor_id
            WHERE e.asset = 'BTC'
            ORDER BY e.elo DESC
            LIMIT ?
            """,
            [limit],
        ) as cur:
            rows = await cur.fetchall()

        entries = [
            SeasonLeaderboardEntry(
                rank=row["rank"],
                competitor_id=str(row["id"]),
                name=row["name"],
                elo=row["elo"],
                tier=Tier(row["tier"]),
                matches=row["matches_count"],
            )
            for row in rows
        ]

        return SeasonLeaderboard(season_id=season_id, leaderboard=entries)

    async def apply_soft_reset(self, season_id: str) -> int:
        async with self._db.execute(
            """
            UPDATE elo_ratings
            SET elo = elo + (? - elo) * 0.5
            WHERE asset = 'BTC'
            RETURNING id
            """,
            [ELO_SOFT_RESET_TARGET],
        ) as cur:
            rows = await cur.fetchall()
        return len(rows)

    async def create_next_season(self) -> Season:
        now = datetime.utcnow()
        async with self._db.execute("SELECT MAX(number) as num FROM seasons") as cur:
            last = await cur.fetchone()
        next_num = (last["num"] if last and last["num"] else 0) + 1

        season_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO seasons (id, number, name, started_at, ends_at, total_participants)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            [
                season_id,
                next_num,
                f"Season {next_num}",
                now,
                now + timedelta(days=SEASON_DURATION_DAYS),
            ],
        )

        return Season(
            id=season_id,
            number=next_num,
            name=f"Season {next_num}",
            status=SeasonStatus.ACTIVE,
            started_at=now,
            ends_at=now + timedelta(days=SEASON_DURATION_DAYS),
            days_remaining=SEASON_DURATION_DAYS,
            total_participants=0,
        )

    async def get_fleet(self, asset: str = "BTC") -> dict:
        async with self._db.execute(
            """
            SELECT
                c.id, c.name, c.type,
                e.elo, e.tier, e.matches_count, e.xp
            FROM competitors c
            JOIN elo_ratings e ON e.competitor_id = c.id
            WHERE e.asset = ? AND c.status = 'active'
            ORDER BY e.elo DESC
            """,
            [asset],
        ) as cur:
            rows = await cur.fetchall()

        cards = []
        total_xp = 0
        total_matches = 0
        total_elo = 0
        legendary_count = 0

        for row in rows:
            xp_val = row["xp"] or 0
            total_xp += xp_val
            total_matches += row["matches_count"]
            total_elo += row["elo"]

            level = level_from_xp(xp_val)
            achievements = 0
            rarity = card_rarity_for_achievements(achievements)
            if rarity == CardRarity.LEGENDARY:
                legendary_count += 1

            cards.append(
                {
                    "competitor_id": str(row["id"]),
                    "name": row["name"],
                    "level": level,
                    "tier": row["tier"],
                    "elo": row["elo"],
                    "rarity": rarity.value,
                    "stats": {
                        "matches": row["matches_count"],
                        "wins": 0,
                        "losses": 0,
                        "win_rate": 0,
                        "current_streak": 0,
                        "best_streak": 0,
                        "total_xp": xp_val,
                        "achievement_count": achievements,
                        "traits_unlocked": 0,
                        "calibration_score": 0,
                    },
                    "trait_icons": [],
                    "achievement_badges": [],
                    "card_version": "1.0",
                }
            )

        count = len(cards)
        return {
            "stats": {
                "total_agents": count,
                "avg_level": sum(c["level"] for c in cards) // max(count, 1),
                "total_xp": total_xp,
                "total_matches": total_matches,
                "avg_elo": total_elo // max(count, 1),
                "legendary_count": legendary_count,
                "mission_claimable": 0,
            },
            "cards": cards,
        }
