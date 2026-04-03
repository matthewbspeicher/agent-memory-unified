from __future__ import annotations
import asyncio
import hashlib
import hmac
import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, Response, Query

if TYPE_CHECKING:
    from whatsapp.assistant import WhatsAppAssistant

logger = logging.getLogger(__name__)

MAX_SEEN_IDS = 1000
RATE_LIMIT_PER_MINUTE = 10


def create_webhook_router(
    assistant: WhatsAppAssistant,
    verify_token: str,
    app_secret: str,
    allowed_numbers: str,
) -> APIRouter:
    router = APIRouter(prefix="/webhook", tags=["whatsapp"])
    allowed_set = {n.strip() for n in allowed_numbers.split(",") if n.strip()}
    seen_ids: set[str] = set()
    seen_ids_list: list[str] = []
    rate_counts: dict[str, list[float]] = defaultdict(list)

    def _verify_signature(body: bytes, signature: str) -> bool:
        if not app_secret:
            return False
        expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _is_rate_limited(phone: str) -> bool:
        now = time.time()
        window = [t for t in rate_counts[phone] if now - t < 60]
        rate_counts[phone] = window
        if len(window) >= RATE_LIMIT_PER_MINUTE:
            return True
        rate_counts[phone].append(now)
        return False

    def _dedup(msg_id: str) -> bool:
        if msg_id in seen_ids:
            return True
        seen_ids.add(msg_id)
        seen_ids_list.append(msg_id)
        while len(seen_ids_list) > MAX_SEEN_IDS:
            old = seen_ids_list.pop(0)
            seen_ids.discard(old)
        return False

    @router.get("/whatsapp")
    async def verify(
        request: Request,
        hub_mode: str = Query(alias="hub.mode", default=""),
        hub_token: str = Query(alias="hub.verify_token", default=""),
        hub_challenge: str = Query(alias="hub.challenge", default=""),
    ):
        if hub_mode == "subscribe" and hub_token == verify_token:
            return Response(content=hub_challenge, media_type="text/plain")
        return Response(status_code=403)

    @router.post("/whatsapp")
    async def inbound(request: Request):
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_signature(body, signature):
            return Response(status_code=401)

        data = await request.json()

        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                messages = change.get("value", {}).get("messages", [])
                for msg in messages:
                    phone = msg.get("from", "")
                    msg_id = msg.get("id", "")
                    text = msg.get("text", {}).get("body", "")

                    if not phone or not text:
                        continue
                    if phone not in allowed_set:
                        logger.warning("Message from disallowed number: %s***", phone[:5])
                        continue
                    if _dedup(msg_id):
                        continue
                    if _is_rate_limited(phone):
                        logger.warning("Rate limited: %s***", phone[:5])
                        continue

                    asyncio.create_task(assistant.handle(phone, text, msg_id))

        return Response(status_code=200)

    return router
