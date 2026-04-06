import asyncio
from storage.db import create_db
from config import load_config
from storage.external import ExternalPortfolioStore


async def main():
    config = load_config(env_file=".env")
    db = await create_db(config)
    store = ExternalPortfolioStore(db)
    try:
        bals = await store.get_balances()
        print("Balances:", bals)
    except Exception:
        import traceback

        traceback.print_exc()


asyncio.run(main())
