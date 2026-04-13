import asyncio
import os
import ssl as _ssl
from config import load_config
from storage.postgres import PostgresDB
import asyncpg

async def main():
    config = load_config()
    
    if config.database_ssl:
        ssl_ctx = _ssl.create_default_context()
        if not config.database_ssl_verify:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = _ssl.CERT_NONE
    else:
        ssl_ctx = None

    pool = await asyncpg.create_pool(config.database_url, ssl=ssl_ctx)
    db = PostgresDB(pool)
    
    # Run the table creation independently
    sql = """
    CREATE TABLE IF NOT EXISTS thought_records (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        symbol TEXT NOT NULL,
        action TEXT NOT NULL,
        conviction_score REAL NOT NULL,
        rule_evaluations TEXT,
        memory_context TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_thought_records_agent ON thought_records(agent_name);
    """
    
    print("Executing SQL...")
    await db.executescript(sql)
    print("Done executing SQL.")
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
