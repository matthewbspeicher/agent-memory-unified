import re

with open("trading/competition/store.py", "r") as f:
    text = f.read()

# Replace $1, $2 with ?
text = re.sub(r"\$(\d+)", "?", text)

# Occurrence 1: get_missions
old1 = """            row = await self._db.fetchrow(
                \"\"\"
                SELECT * FROM mission_progress
                WHERE competitor_id = ? AND mission_id = ?
                ORDER BY period_start DESC LIMIT 1
                \"\"\",
                competitor_id,
                mission_id.value,
            )"""
new1 = """            async with self._db.execute(
                \"\"\"
                SELECT * FROM mission_progress
                WHERE competitor_id = ? AND mission_id = ?
                ORDER BY period_start DESC LIMIT 1
                \"\"\",
                [competitor_id, mission_id.value],
            ) as cur:
                row = await cur.fetchone()"""
text = text.replace(old1, new1)

# Occurrence 2: update_mission_progress
old2 = """        row = await self._db.fetchrow(
            \"\"\"
            INSERT INTO mission_progress (
                id, competitor_id, mission_id, progress, target,
                completed, claimed, xp_awarded, period_start, period_end, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (competitor_id, mission_id, period_start)
            DO UPDATE SET
                progress = LEAST(mission_progress.progress + ?, mission_progress.target),
                completed = CASE
                    WHEN mission_progress.progress + ? >= mission_progress.target THEN TRUE
                    ELSE mission_progress.completed
                END,
                updated_at = ?
            RETURNING *
            \"\"\",
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
        )"""
new2 = """        async with self._db.execute(
            \"\"\"
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
            \"\"\",
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
            row = await cur.fetchone()"""
text = text.replace(old2, new2)

# Occurrence 3: claim_mission_reward
old3 = """        row = await self._db.fetchrow(
            \"\"\"
            UPDATE mission_progress
            SET claimed = TRUE, xp_awarded = ?, updated_at = ?
            WHERE competitor_id = ? AND mission_id = ?
                AND completed = TRUE AND claimed = FALSE
            RETURNING *
            \"\"\",
            competitor_id,
            mission_id.value,
            info["xp_reward"],
            datetime.utcnow(),
        )"""
new3 = """        async with self._db.execute(
            \"\"\"
            UPDATE mission_progress
            SET claimed = TRUE, xp_awarded = ?, updated_at = ?
            WHERE competitor_id = ? AND mission_id = ?
                AND completed = TRUE AND claimed = FALSE
            RETURNING *
            \"\"\",
            [info["xp_reward"], datetime.utcnow(), competitor_id, mission_id.value],
        ) as cur:
            row = await cur.fetchone()"""
text = text.replace(old3, new3)

# Occurrence 4: get_seasons
old4 = """        rows = await self._db.fetch(
            "SELECT * FROM seasons ORDER BY number DESC LIMIT 10"
        )"""
new4 = """        async with self._db.execute("SELECT * FROM seasons ORDER BY number DESC LIMIT 10") as cur:
            rows = await cur.fetchall()"""
text = text.replace(old4, new4)

# Occurrence 5: get_season_leaderboard
old5 = """        rows = await self._db.fetch(
            \"\"\"
            SELECT
                ROW_NUMBER() OVER (ORDER BY elo DESC) as rank,
                c.id, c.name, e.elo, e.tier, e.matches_count
            FROM elo_ratings e
            JOIN competitors c ON c.id = e.competitor_id
            WHERE e.asset = 'BTC'
            ORDER BY e.elo DESC
            LIMIT ?
            \"\"\",
            limit,
        )"""
new5 = """        async with self._db.execute(
            \"\"\"
            SELECT
                ROW_NUMBER() OVER (ORDER BY elo DESC) as rank,
                c.id, c.name, e.elo, e.tier, e.matches_count
            FROM elo_ratings e
            JOIN competitors c ON c.id = e.competitor_id
            WHERE e.asset = 'BTC'
            ORDER BY e.elo DESC
            LIMIT ?
            \"\"\",
            [limit],
        ) as cur:
            rows = await cur.fetchall()"""
text = text.replace(old5, new5)

# Occurrence 6: apply_soft_reset
old6 = """        rows = await self._db.fetch(
            \"\"\"
            UPDATE elo_ratings
            SET elo = elo + (? - elo) * 0.5
            WHERE asset = 'BTC'
            RETURNING id
            \"\"\",
            ELO_SOFT_RESET_TARGET,
        )"""
new6 = """        async with self._db.execute(
            \"\"\"
            UPDATE elo_ratings
            SET elo = elo + (? - elo) * 0.5
            WHERE asset = 'BTC'
            RETURNING id
            \"\"\",
            [ELO_SOFT_RESET_TARGET],
        ) as cur:
            rows = await cur.fetchall()"""
text = text.replace(old6, new6)

# Occurrence 7a: create_next_season row
old7a = """        last = await self._db.fetchrow("SELECT MAX(number) as num FROM seasons")"""
new7a = """        async with self._db.execute("SELECT MAX(number) as num FROM seasons") as cur:
            last = await cur.fetchone()"""
text = text.replace(old7a, new7a)

# Occurrence 7b: create_next_season execute
old7b = """        await self._db.execute(
            \"\"\"
            INSERT INTO seasons (id, number, name, started_at, ends_at, total_participants)
            VALUES (?, ?, ?, ?, ?, 0)
            \"\"\",
            season_id,
            next_num,
            f"Season {next_num}",
            now,
            now + timedelta(days=SEASON_DURATION_DAYS),
        )"""
new7b = """        await self._db.execute(
            \"\"\"
            INSERT INTO seasons (id, number, name, started_at, ends_at, total_participants)
            VALUES (?, ?, ?, ?, ?, 0)
            \"\"\",
            [
                season_id,
                next_num,
                f"Season {next_num}",
                now,
                now + timedelta(days=SEASON_DURATION_DAYS),
            ],
        )"""
text = text.replace(old7b, new7b)

# Occurrence 8: get_fleet
old8 = """        rows = await self._db.fetch(
            \"\"\"
            SELECT
                c.id, c.name, c.type,
                e.elo, e.tier, e.matches_count, e.xp
            FROM competitors c
            JOIN elo_ratings e ON e.competitor_id = c.id
            WHERE e.asset = ? AND c.status = 'active'
            ORDER BY e.elo DESC
            \"\"\",
            asset,
        )"""
new8 = """        async with self._db.execute(
            \"\"\"
            SELECT
                c.id, c.name, c.type,
                e.elo, e.tier, e.matches_count, e.xp
            FROM competitors c
            JOIN elo_ratings e ON e.competitor_id = c.id
            WHERE e.asset = ? AND c.status = 'active'
            ORDER BY e.elo DESC
            \"\"\",
            [asset],
        ) as cur:
            rows = await cur.fetchall()"""
text = text.replace(old8, new8)

with open("trading/competition/store.py", "w") as f:
    f.write(text)
print("Fixes applied successfully to store.py")
