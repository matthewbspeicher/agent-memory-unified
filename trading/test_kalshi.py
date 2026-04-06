import asyncio
import os
from adapters.kalshi.client import KalshiClient


async def main():
    try:
        from dotenv import load_dotenv

        load_dotenv("../.env")
        client = KalshiClient(
            key_id=os.environ.get("STA_KALSHI_KEY_ID"),
            private_key_path=os.environ.get("STA_KALSHI_PRIVATE_KEY_PATH"),
            demo=False,
        )
        print("balance:", await client.get_balance())
    except Exception as e:
        print("Error:", e)
        if hasattr(e, "response") and e.response is not None:
            print("Response:", e.response.text)


if __name__ == "__main__":
    asyncio.run(main())
