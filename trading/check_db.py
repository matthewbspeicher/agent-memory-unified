import asyncio
import os
import ssl as _ssl
from config import load_config
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

    conn = await asyncpg.connect(config.database_url, ssl=ssl_ctx)
    row = await conn.fetchrow(
        "SELECT data_type FROM information_schema.columns WHERE table_name = 'signal_features' AND column_name = 'opportunity_timestamp'"
    )
    print(f"Data type: {row['data_type'] if row else 'NOT FOUND'}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
