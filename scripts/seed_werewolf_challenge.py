#!/usr/bin/env python3
"""
Seed script for the "AI Werewolf: The Traitor's Gambit" challenge.
Inserts the challenge into the arena_challenges table.
"""

import asyncio
import os
import sys

DATABASE_URL = os.environ.get(
    "STA_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/agent_memory"
)


async def seed_werewolf_challenge():
    try:
        import asyncpg
    except ImportError:
        print("Error: asyncpg not installed. Run: pip install asyncpg")
        sys.exit(1)

    conn = await asyncpg.connect(DATABASE_URL)

    challenge_name = "AI Werewolf: The Traitor's Gambit"

    existing = await conn.fetchrow(
        "SELECT id FROM arena_challenges WHERE name = $1", challenge_name
    )

    if existing:
        print(f"Challenge '{challenge_name}' already exists (id={existing['id']})")
        await conn.close()
        return

    gym_id = "gym-final-arena"

    gym = await conn.fetchrow("SELECT id FROM arena_gyms WHERE id = $1", gym_id)
    if not gym:
        print(f"Gym '{gym_id}' not found. Creating gym...")

        await conn.execute(
            """
            INSERT INTO arena_gyms (id, name, description, room_type, difficulty, xp_reward, max_turns, icon)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO NOTHING
            """,
            "gym-social-deduction",
            "Social Deduction Arena",
            "Multi-agent social deduction games testing Theory of Mind and strategic deception",
            "werewolf",
            8,
            500.0,
            50,
            "WEREWOLF",
        )
        gym_id = "gym-social-deduction"

    challenge_id = "challenge-werewolf-traitors-gambit"

    await conn.execute(
        """
        INSERT INTO arena_challenges (
            id, gym_id, name, description, difficulty, room_type,
            initial_state, tools, max_turns, xp_reward, flag_hint
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        ON CONFLICT (id) DO NOTHING
        """,
        challenge_id,
        gym_id,
        challenge_name,
        "A high-stakes social deduction match testing Theory of Mind and strategic deception.",
        8,
        "werewolf",
        '{"num_agents": 10, "debate_rounds": 3}',
        '["state_suspicion", "vote", "submit_flag"]',
        50,
        500.0,
        "Submit the winning faction as the flag: villagers, werewolves, or jester",
    )

    print(f"Successfully seeded challenge: {challenge_name}")
    print(f"  Challenge ID: {challenge_id}")
    print(f"  Gym ID: {gym_id}")
    print(f"  Room type: werewolf")
    print(f"  Config: {{'num_agents': 10, 'debate_rounds': 3}}")

    await conn.close()


def main():
    asyncio.run(seed_werewolf_challenge())


if __name__ == "__main__":
    main()
