from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notifications.base import Notifier

logger = logging.getLogger(__name__)


class AlertRouter:
    """Routes system events to the CompositeNotifier by alert tier.

    Critical  -> immediate WhatsApp message via notifier.send_text()
    Warning   -> buffered; flushed every 15 min as a single digest message
    Info      -> no notification (Supabase only)
    """

    def __init__(self, notifier: "Notifier") -> None:
        self._notifier = notifier
        self._warning_buffer: list[str] = []
        self._flush_task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the background 15-minute warning flush loop."""
        self._flush_task = asyncio.create_task(self._flush_loop())

    def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()

    async def fire(
        self,
        level: str,
        event_type: str,
        message: str,
        metadata: dict,
    ) -> None:
        if level == "critical":
            text = f"CRITICAL | {event_type}\n{message}"
            if metadata:
                text += f"\n{metadata}"
            await self._send(text)
        elif level == "warning":
            self._warning_buffer.append(f"* [{event_type}] {message}")
        # info -> no notification

    async def flush_warnings(self) -> None:
        if not self._warning_buffer:
            return
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")
        lines = "\n".join(self._warning_buffer)
        text = f"WARNING DIGEST ({now})\n{lines}"
        self._warning_buffer.clear()
        await self._send(text)

    async def _send(self, text: str) -> None:
        try:
            await self._notifier.send_text(text)
        except Exception:
            logger.exception("AlertRouter failed to send notification")

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(15 * 60)
            await self.flush_warnings()
