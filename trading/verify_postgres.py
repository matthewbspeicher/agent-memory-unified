"""
Quick verification that Python can read/write to Postgres tables.
"""
import asyncio
import asyncpg
import os

async def verify():
    # Connect directly with asyncpg
    conn = await asyncpg.connect(
        "postgresql://postgres:secret@127.0.0.1:5432/agent_memory"
    )

    # Test 1: Read from agent_registry
    result = await conn.fetchval("SELECT COUNT(*) FROM agent_registry")
    print(f"✓ agent_registry: {result} rows")

    # Test 2: Read from opportunities
    result = await conn.fetchval("SELECT COUNT(*) FROM opportunities")
    print(f"✓ opportunities: {result} rows")

    # Test 3: Read from tracked_positions
    result = await conn.fetchval("SELECT COUNT(*) FROM tracked_positions")
    print(f"✓ tracked_positions: {result} rows")

    # Test 4: Write a test agent (using proper column names)
    await conn.execute("""
        INSERT INTO agent_registry (
            name, strategy, schedule, interval_or_cron, universe, parameters,
            status, trust_level, runtime_overrides, promotion_criteria,
            shadow_mode, created_by, generation, creation_context
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ON CONFLICT (name) DO NOTHING
    """, "test_agent", "test_strategy", "continuous", 60, "[]", "{}",
        "active", "bronze", "{}", "{}", False, "verify_script", 1, "{}")
    print("✓ Write to agent_registry")

    # Test 5: Read it back
    result = await conn.fetchrow(
        "SELECT name, trust_level FROM agent_registry WHERE name = $1",
        "test_agent"
    )
    print(f"✓ Read back: {result['name']} ({result['trust_level']})")

    # Cleanup
    await conn.execute("DELETE FROM agent_registry WHERE name = $1", "test_agent")
    print("✓ Cleanup complete")

    await conn.close()
    print("\n✅ All Postgres operations working!")

if __name__ == "__main__":
    asyncio.run(verify())
