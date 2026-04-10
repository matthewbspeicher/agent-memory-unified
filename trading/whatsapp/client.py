from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from collections.abc import Mapping
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)

META_API_BASE = "https://graph.facebook.com/v22.0"


class WhatsAppClient:
    def __init__(self, phone_id: str, token: str, app_secret: str) -> None:
        self._phone_id = phone_id
        self._token = token
        self._app_secret = app_secret
        self._sessions: dict[str, datetime] = {}
        self._auth_failed: bool = False
        self._last_error_key: str | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str = "messages") -> str:
        return f"{META_API_BASE}/{self._phone_id}/{path}"

    def record_inbound(self, phone: str) -> None:
        self._sessions[phone] = datetime.now(timezone.utc)

    def is_within_window(self, phone: str) -> bool:
        last = self._sessions.get(phone)
        if not last:
            return False
        return datetime.now(timezone.utc) - last < timedelta(hours=24)

    async def load_sessions(self, db) -> None:
        try:
            cursor = await db.execute(
                "SELECT phone, last_inbound_at FROM whatsapp_sessions"
            )
            rows = cast(list[Mapping[str, Any]], await cursor.fetchall())
            for row in rows:
                self._sessions[str(row["phone"])] = datetime.fromisoformat(
                    str(row["last_inbound_at"])
                ).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    async def persist_session(self, db, phone: str) -> None:
        ts = self._sessions.get(phone)
        if ts:
            await db.execute(
                "INSERT OR REPLACE INTO whatsapp_sessions (phone, last_inbound_at) VALUES (?, ?)",
                (phone, ts.isoformat()),
            )
            await db.commit()

    def _handle_error_response(self, method: str, status_code: int, text: str) -> None:
        """Classify and suppress repeated WhatsApp API errors."""
        if status_code == 401 or "invalid parameter" in text.lower():
            if not self._auth_failed:
                logger.warning(
                    "WhatsApp auth failed (%s %s) — suppressing further errors",
                    status_code,
                    text[:200],
                )
                self._auth_failed = True
            return
        error_key = f"{method}:{status_code}"
        if error_key != self._last_error_key:
            logger.error("WhatsApp %s failed: %s %s", method, status_code, text[:200])
            self._last_error_key = error_key

    async def send_text(self, to: str, body: str) -> None:
        if self._auth_failed:
            return
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._url(), headers=self._headers(), json=payload)
            if resp.status_code != 200:
                self._handle_error_response("send_text", resp.status_code, resp.text)

    async def send_image(
        self, to: str, image_bytes: bytes, caption: str | None = None
    ) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upload_resp = await client.post(
                f"{META_API_BASE}/{self._phone_id}/media",
                headers={"Authorization": f"Bearer {self._token}"},
                files={"file": ("chart.png", image_bytes, "image/png")},
                data={"messaging_product": "whatsapp", "type": "image/png"},
            )
            if upload_resp.status_code != 200:
                logger.error("WhatsApp media upload failed: %s", upload_resp.text)
                return
            media_id = upload_resp.json().get("id")

        image_payload: dict[str, str] = {"id": media_id}
        if caption:
            image_payload["caption"] = caption

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": image_payload,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(self._url(), headers=self._headers(), json=payload)

    async def send_template(
        self, to: str, template_name: str, parameters: list[str]
    ) -> None:
        if self._auth_failed:
            return
        components = []
        if parameters:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in parameters],
                }
            )
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en_US"},
                "components": components,
            },
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._url(), headers=self._headers(), json=payload)
            if resp.status_code != 200:
                self._handle_error_response(
                    "send_template", resp.status_code, resp.text
                )

    async def mark_read(self, message_id: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(self._url(), headers=self._headers(), json=payload)
