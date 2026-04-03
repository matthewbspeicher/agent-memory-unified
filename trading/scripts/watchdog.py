#!/usr/bin/env python3
"""WSL2 reliability watchdog.

Polls GET /health on the main trading API every 60s.
If no response for > 5 minutes, sends a WhatsApp alert directly
via the Meta Cloud API using WHATSAPP_API_KEY env var.

Run as a separate process:
  python scripts/watchdog.py

Or via systemd -- see scripts/stock-trading-watchdog.service
"""
import asyncio
import logging
import os
import time
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("watchdog")

API_URL = os.environ.get("STA_WATCHDOG_API_URL", "http://127.0.0.1:8000/health")
POLL_INTERVAL = int(os.environ.get("STA_WATCHDOG_POLL_INTERVAL", "60"))
SILENCE_THRESHOLD = int(os.environ.get("STA_WATCHDOG_SILENCE_THRESHOLD", "300"))
WA_PHONE_ID = os.environ.get("STA_WHATSAPP_PHONE_ID", "")
WA_TOKEN = os.environ.get("STA_WHATSAPP_TOKEN", "")
WA_TO = os.environ.get("STA_WHATSAPP_ALLOWED_NUMBERS", "")


async def send_whatsapp_alert(message: str) -> None:
    if not WA_PHONE_ID or not WA_TOKEN or not WA_TO:
        logger.warning("WhatsApp not configured -- cannot send watchdog alert")
        return
    to = WA_TO.split(",")[0].strip()
    url = f"https://graph.facebook.com/v18.0/{WA_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {WA_TOKEN}"},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("WhatsApp alert sent to %s", to)
        except Exception as exc:
            logger.error("Failed to send WhatsApp alert: %s", exc)


async def run() -> None:
    last_ok = time.monotonic()
    alert_sent_at: float | None = None
    logger.info("Watchdog started. Polling %s every %ds", API_URL, POLL_INTERVAL)

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(API_URL, timeout=10)
                resp.raise_for_status()
            last_ok = time.monotonic()
            alert_sent_at = None
            logger.debug("Health check OK")
        except Exception as exc:
            elapsed = time.monotonic() - last_ok
            logger.warning("Health check failed (%.0fs silent): %s", elapsed, exc)
            if elapsed > SILENCE_THRESHOLD:
                # Avoid spamming -- send at most once per silence window
                if alert_sent_at is None or (time.monotonic() - alert_sent_at) > SILENCE_THRESHOLD:
                    alert_sent_at = time.monotonic()
                    await send_whatsapp_alert(
                        f"WATCHDOG: Stock Trading API has been silent for "
                        f"{int(elapsed)}s. Check WSL2 process on host."
                    )


if __name__ == "__main__":
    asyncio.run(run())
