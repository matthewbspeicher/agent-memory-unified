# trading/competition/store.py

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from competition.models import (
    AgentCard,
    AgentLineage,
    AgentTrait,
    BetResult,
    BetStatus,
    BettingPool,
    BreedResult,
    CardRarity,
    CardStats,
    CompetitorCreate,
    CompetitorRecord,
    CompetitorType,
    CompetitorXP,
    EloRating,
    LeaderboardEntry,
    MatchBet,
    MissionId,
    MissionProgress,
    MissionResponse,
    MissionType,
    Mutation,
    MutationRarity,
    Season,
    SeasonLeaderboard,
    SeasonLeaderboardEntry,
    SeasonStatus,
    Tier,
    TraitLoadout,
    TraitUnlock,
    XpHistoryEntry,
    XpSource,
    BETTING_HOUSE_CUT,
    BREEDING_COOLDOWN_HOURS,
    CARD_RARITY_THRESHOLDS,
    ELO_SOFT_RESET_TARGET,
    MAX_BET_XP,
    MISSION_INFO,
    MIN_BET_XP,
    MUTATION_CHANCE_PER_LEVEL,
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
        async with self._db.execute(
            "SELECT * FROM seasons ORDER BY number DESC LIMIT 10"
        ) as cur:
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

    async def get_betting_pool(self, match_id: str) -> BettingPool:
        row = await self._db.fetchrow(
            """
            SELECT
                match_id,
                COALESCE(SUM(amount), 0) as total_pool,
                COALESCE(SUM(CASE WHEN predicted_winner = competitor_a THEN amount ELSE 0 END), 0) as a_pool,
                COALESCE(SUM(CASE WHEN predicted_winner = competitor_b THEN amount ELSE 0 END), 0) as b_pool,
                COUNT(CASE WHEN predicted_winner = competitor_a THEN 1 END) as a_bettors,
                COUNT(CASE WHEN predicted_winner = competitor_b THEN 1 END) as b_bettors
            FROM match_bets
            WHERE match_id = $1 AND status = 'open'
            """,
            match_id,
        )

        return BettingPool(
            match_id=match_id,
            total_pool=row["total_pool"] if row else 0,
            competitor_a_pool=row["a_pool"] if row else 0,
            competitor_b_pool=row["b_pool"] if row else 0,
            competitor_a_bettors=row["a_bettors"] if row else 0,
            competitor_b_bettors=row["b_bettors"] if row else 0,
            status=BetStatus.OPEN,
        )

    async def place_bet(
        self,
        match_id: str,
        better_id: str,
        predicted_winner: str,
        amount: int,
        competitor_a: str,
        competitor_b: str,
    ) -> MatchBet:
        if amount < MIN_BET_XP:
            raise ValueError(f"Minimum bet is {MIN_BET_XP} XP")
        if amount > MAX_BET_XP:
            raise ValueError(f"Maximum bet is {MAX_BET_XP} XP")

        if predicted_winner not in (competitor_a, competitor_b):
            raise ValueError("Predicted winner must be one of the competitors")

        bet_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self._db.execute(
            """
            INSERT INTO match_bets (id, match_id, better_id, predicted_winner, amount, status, created_at)
            VALUES ($1, $2, $3, $4, $5, 'open', $6)
            """,
            bet_id,
            match_id,
            better_id,
            predicted_winner,
            amount,
            now,
        )

        return MatchBet(
            id=bet_id,
            match_id=match_id,
            better_id=better_id,
            predicted_winner=predicted_winner,
            amount=amount,
            potential_payout=amount,
            status=BetStatus.OPEN,
            created_at=now,
        )

    async def settle_match_bets(self, match_id: str, winner_id: str) -> BetResult:
        pool = await self.get_betting_pool(match_id)
        if pool.status != BetStatus.OPEN:
            raise ValueError("Betting pool already settled")

        winner_pool = (
            pool.competitor_a_pool
            if winner_id == pool.competitor_a
            else pool.competitor_b_pool
        )

        if winner_pool == 0:
            await self._db.execute(
                "UPDATE match_bets SET status = 'cancelled' WHERE match_id = $1",
                match_id,
            )
            return BetResult(
                match_id=match_id,
                winner=winner_id,
                total_pool=pool.total_pool,
                house_cut=0,
                distributed=0,
                settled_bets=0,
            )

        house_cut = int(pool.total_pool * BETTING_HOUSE_CUT)
        distributable = pool.total_pool - house_cut
        now = datetime.utcnow()

        rows = await self._db.fetch(
            """
            UPDATE match_bets
            SET status = 'settled',
                payout = CAST(CEIL(amount::float / $1 * $2) AS INTEGER),
                settled_at = $3
            WHERE match_id = $4 AND predicted_winner = $5 AND status = 'open'
            RETURNING id, payout
            """,
            winner_pool,
            distributable,
            now,
            match_id,
            winner_id,
        )

        await self._db.execute(
            """
            UPDATE match_bets
            SET status = 'cancelled', payout = 0, settled_at = $2
            WHERE match_id = $1 AND predicted_winner != $3 AND status = 'open'
            """,
            match_id,
            now,
            winner_id,
        )

        total_distributed = sum(r["payout"] for r in rows)

        return BetResult(
            match_id=match_id,
            winner=winner_id,
            total_pool=pool.total_pool,
            house_cut=house_cut,
            distributed=total_distributed,
            settled_bets=len(rows),
        )

    async def get_match_bets(
        self, match_id: str, better_id: str | None = None
    ) -> list[MatchBet]:
        query = "SELECT * FROM match_bets WHERE match_id = $1"
        params: list[Any] = [match_id]

        if better_id:
            query += " AND better_id = $2"
            params.append(better_id)

        query += " ORDER BY created_at DESC"

        rows = await self._db.fetch(query, *params)

        return [
            MatchBet(
                id=str(r["id"]),
                match_id=str(r["match_id"]),
                better_id=str(r["better_id"]),
                predicted_winner=str(r["predicted_winner"]),
                amount=r["amount"],
                potential_payout=r["amount"],
                status=BetStatus(r["status"]),
                created_at=r["created_at"],
                settled_at=r.get("settled_at"),
                payout=r.get("payout", 0),
            )
            for r in rows
        ]

    async def process_level_up(
        self, competitor_id: str, new_level: int, asset: str = "BTC"
    ) -> Mutation | None:
        import random

        await self.auto_unlock_traits(competitor_id, new_level)

        mutation = None
        if random.random() < MUTATION_CHANCE_PER_LEVEL:
            available_traits = list(AgentTrait)
            trait = random.choice(available_traits)

            roll = random.random()
            if roll < 0.05:
                rarity = MutationRarity.LEGENDARY
                multiplier = 2.5
            elif roll < 0.20:
                rarity = MutationRarity.RARE
                multiplier = 1.8
            elif roll < 0.50:
                rarity = MutationRarity.UNCOMMON
                multiplier = 1.3
            else:
                rarity = MutationRarity.COMMON
                multiplier = 1.1

            mutation_id = str(uuid.uuid4())
            await self._db.execute(
                """
                INSERT INTO agent_mutations (id, agent_id, trait, rarity, bonus_multiplier, level_obtained, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                mutation_id,
                competitor_id,
                trait.value,
                rarity.value,
                multiplier,
                new_level,
                datetime.utcnow(),
            )

            mutation = Mutation(
                id=mutation_id,
                agent_id=competitor_id,
                trait=trait,
                rarity=rarity,
                bonus_multiplier=multiplier,
                level_obtained=new_level,
                created_at=datetime.utcnow(),
            )

        return mutation

    async def get_mutations(self, agent_id: str) -> list[Mutation]:
        rows = await self._db.fetch(
            """
            SELECT id, agent_id, trait, rarity, bonus_multiplier, level_obtained, created_at
            FROM agent_mutations
            WHERE agent_id = $1
            ORDER BY level_obtained DESC
            """,
            agent_id,
        )

        return [
            Mutation(
                id=str(r["id"]),
                agent_id=str(r["agent_id"]),
                trait=AgentTrait(r["trait"]),
                rarity=MutationRarity(r["rarity"]),
                bonus_multiplier=r["bonus_multiplier"],
                level_obtained=r["level_obtained"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def get_lineage(self, agent_id: str) -> AgentLineage | None:
        row = await self._db.fetchrow(
            """
            SELECT id, agent_id, parent_a_id, parent_b_id, generation, breeding_count, last_breed_at, created_at
            FROM agent_lineage
            WHERE agent_id = $1
            """,
            agent_id,
        )

        if not row:
            return None

        return AgentLineage(
            id=str(row["id"]),
            agent_id=str(row["agent_id"]),
            parent_a_id=str(row["parent_a_id"]) if row["parent_a_id"] else None,
            parent_b_id=str(row["parent_b_id"]) if row["parent_b_id"] else None,
            generation=row["generation"],
            breeding_count=row["breeding_count"],
            last_breed_at=row.get("last_breed_at"),
            created_at=row.get("created_at"),
        )

    async def can_breed(self, agent_id: str) -> bool:
        lineage = await self.get_lineage(agent_id)
        if not lineage:
            return True
        if lineage.last_breed_at is None:
            return True
        cooldown_end = lineage.last_breed_at + timedelta(hours=BREEDING_COOLDOWN_HOURS)
        return datetime.utcnow() >= cooldown_end

    async def breed_agents(
        self, parent_a_id: str, parent_b_id: str, child_name: str
    ) -> BreedResult:
        import random

        if not await self.can_breed(parent_a_id):
            raise ValueError(f"Agent {parent_a_id} is on breeding cooldown")
        if not await self.can_breed(parent_b_id):
            raise ValueError(f"Agent {parent_b_id} is on breeding cooldown")

        parent_a_traits = await self.get_unlocked_traits(parent_a_id)
        parent_b_traits = await self.get_unlocked_traits(parent_b_id)

        all_traits = list(set(parent_a_traits + parent_b_traits))
        num_inherited = min(3, len(all_traits))
        inherited = random.sample(all_traits, num_inherited)

        mutated_trait = None
        mutation_rarity = None
        roll = random.random()
        if roll < 0.25:
            available = [t for t in list(AgentTrait) if t not in inherited]
            if available:
                mutated_trait = random.choice(available)
                if roll < 0.05:
                    mutation_rarity = MutationRarity.LEGENDARY
                elif roll < 0.15:
                    mutation_rarity = MutationRarity.RARE
                else:
                    mutation_rarity = MutationRarity.UNCOMMON

        parent_a_lineage = await self.get_lineage(parent_a_id)
        parent_b_lineage = await self.get_lineage(parent_b_id)
        gen_a = parent_a_lineage.generation if parent_a_lineage else 0
        gen_b = parent_b_lineage.generation if parent_b_lineage else 0
        child_generation = max(gen_a, gen_b) + 1

        child_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO agent_lineage (id, agent_id, parent_a_id, parent_b_id, generation, breeding_count, created_at)
            VALUES ($1, $2, $3, $4, $5, 0, $6)
            """,
            child_id,
            child_id,
            parent_a_id,
            parent_b_id,
            child_generation,
            datetime.utcnow(),
        )

        await self._db.execute(
            """
            UPDATE agent_lineage
            SET breeding_count = breeding_count + 1, last_breed_at = $1
            WHERE agent_id IN ($2, $3)
            """,
            datetime.utcnow(),
            parent_a_id,
            parent_b_id,
        )

        all_inherited = inherited.copy()
        if mutated_trait:
            all_inherited.append(mutated_trait)

        for trait in all_inherited:
            await self.unlock_trait(child_id, trait, 0)

        return BreedResult(
            child_id=child_id,
            child_name=child_name,
            inherited_traits=inherited,
            mutated_trait=mutated_trait,
            mutation_rarity=mutation_rarity,
            generation=child_generation,
        )

    async def get_arena_gyms(self) -> list[dict]:
        """Get all arena gyms with challenge counts."""
        rows = await self._db.fetch(
            """
            SELECT g.id, g.name, g.description, g.room_type, g.difficulty,
                   g.xp_reward, g.max_turns, g.icon,
                   COUNT(c.id) as challenge_count
            FROM arena_gyms g
            LEFT JOIN arena_challenges c ON c.gym_id = g.id
            GROUP BY g.id
            ORDER BY g.difficulty
            """
        )
        return [dict(r) for r in rows]

    async def get_arena_challenges(self, gym_id: str | None = None) -> list[dict]:
        """Get challenges, optionally filtered by gym."""
        if gym_id:
            rows = await self._db.fetch(
                "SELECT * FROM arena_challenges WHERE gym_id = $1 ORDER BY difficulty",
                gym_id,
            )
        else:
            rows = await self._db.fetch(
                "SELECT * FROM arena_challenges ORDER BY difficulty"
            )
        return [dict(r) for r in rows]

    async def start_arena_session(self, challenge_id: str, agent_id: str) -> dict:
        """Start a new arena session for an agent."""
        challenge = await self._db.fetchrow(
            "SELECT * FROM arena_challenges WHERE id = $1", challenge_id
        )
        if not challenge:
            raise ValueError("Challenge not found")

        session_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self._db.execute(
            """
            INSERT INTO arena_sessions (id, challenge_id, agent_id, current_state, inventory, turn_count, score, status, created_at)
            VALUES ($1, $2, $3, 'start', '[]', 0, 0.0, 'active', $4)
            """,
            session_id,
            challenge_id,
            agent_id,
            now,
        )

        return {
            "id": session_id,
            "challenge_id": challenge_id,
            "agent_id": agent_id,
            "current_state": "start",
            "inventory": [],
            "turn_count": 0,
            "score": 0.0,
            "status": "active",
        }

    async def execute_arena_turn(
        self, session_id: str, tool_name: str, kwargs: dict
    ) -> dict:
        """Execute a tool in an arena session."""
        session = await self._db.fetchrow(
            "SELECT * FROM arena_sessions WHERE id = $1", session_id
        )
        if not session:
            raise ValueError("Session not found")
        if session["status"] != "active":
            raise ValueError("Session is not active")

        challenge = await self._db.fetchrow(
            "SELECT * FROM arena_challenges WHERE id = $1", session["challenge_id"]
        )

        if tool_name not in json.loads(challenge["tools"]):
            output = f"Tool '{tool_name}' not available in this challenge"
            score_delta = -0.1
        else:
            output = f"Executed {tool_name} with {kwargs}"
            score_delta = 0.1

        turn_count = session["turn_count"] + 1
        new_score = session["score"] + score_delta
        status = "active"

        if turn_count >= challenge["max_turns"]:
            status = "failed"
        if tool_name == "submit_flag":
            flag = kwargs.get("flag", "")
            if flag == challenge["flag_hash"]:
                status = "completed"
                new_score += 10.0
                output = "FLAG ACCEPTED! Challenge complete!"
            else:
                output = "Incorrect flag"
                score_delta = -0.5

        turn_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO arena_turns (id, session_id, turn_number, tool_name, tool_input, tool_output, score_delta, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            turn_id,
            session_id,
            turn_count,
            tool_name,
            json.dumps(kwargs),
            output,
            score_delta,
            datetime.utcnow(),
        )

        await self._db.execute(
            """
            UPDATE arena_sessions
            SET turn_count = $1, score = $2, status = $3, completed_at = CASE WHEN $3 != 'active' THEN $4 ELSE NULL END
            WHERE id = $5
            """,
            turn_count,
            new_score,
            status,
            datetime.utcnow() if status != "active" else None,
            session_id,
        )

        return {
            "id": turn_id,
            "turn_number": turn_count,
            "tool_name": tool_name,
            "tool_input": kwargs,
            "tool_output": output,
            "score_delta": score_delta,
            "status": status,
        }

    async def get_arena_session(self, session_id: str) -> dict | None:
        """Get session details with turns."""
        session = await self._db.fetchrow(
            "SELECT * FROM arena_sessions WHERE id = $1", session_id
        )
        if not session:
            return None

        turns = await self._db.fetch(
            "SELECT * FROM arena_turns WHERE session_id = $1 ORDER BY turn_number",
            session_id,
        )

        return {
            **dict(session),
            "turns": [dict(t) for t in turns],
        }

    async def get_arena_challenge(self, challenge_id: str) -> dict | None:
        row = await self._db.fetchrow(
            "SELECT * FROM arena_challenges WHERE id = $1", challenge_id
        )
        return dict(row) if row else None

    async def place_arena_bet(
        self,
        session_id: str,
        better_id: str,
        predicted_winner: str,
        amount: int,
    ) -> dict:
        if amount < MIN_BET_XP:
            raise ValueError(f"Minimum bet is {MIN_BET_XP} XP")
        if amount > MAX_BET_XP:
            raise ValueError(f"Maximum bet is {MAX_BET_XP} XP")

        session = await self.get_arena_session(session_id)
        if not session:
            raise ValueError("Session not found")

        session_players = ["player_a", "player_b"]
        if predicted_winner not in session_players:
            raise ValueError(f"Predicted winner must be one of: {session_players}")

        bet_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self._db.execute(
            """
            INSERT INTO match_bets (id, match_id, better_id, predicted_winner, amount, status, created_at)
            VALUES ($1, $2, $3, $4, $5, 'open', $6)
            """,
            bet_id,
            session_id,
            better_id,
            predicted_winner,
            amount,
            now,
        )

        return {
            "id": bet_id,
            "better_id": better_id,
            "predicted_winner": predicted_winner,
            "amount": amount,
            "potential_payout": amount,
            "status": "open",
        }

    async def get_arena_betting_pool(self, session_id: str) -> dict:
        row = await self._db.fetchrow(
            """
            SELECT
                COALESCE(SUM(amount), 0) as total_pool,
                COALESCE(SUM(CASE WHEN predicted_winner = 'player_a' THEN amount ELSE 0 END), 0) as a_pool,
                COALESCE(SUM(CASE WHEN predicted_winner = 'player_b' THEN amount ELSE 0 END), 0) as b_pool,
                COUNT(CASE WHEN predicted_winner = 'player_a' THEN 1 END) as a_bettors,
                COUNT(CASE WHEN predicted_winner = 'player_b' THEN 1 END) as b_bettors
            FROM match_bets
            WHERE match_id = $1 AND status = 'open'
            """,
            session_id,
        )

        total = row["total_pool"] if row else 0
        a_pool = row["a_pool"] if row else 0
        b_pool = row["b_pool"] if row else 0

        a_odds = a_pool / total if total > 0 else 0.5
        b_odds = b_pool / total if total > 0 else 0.5

        return {
            "total_pool": total,
            "player_a_pool": a_pool,
            "player_b_pool": b_pool,
            "player_a_odds": round(a_odds, 2),
            "player_b_odds": round(b_odds, 2),
            "status": "open",
        }
