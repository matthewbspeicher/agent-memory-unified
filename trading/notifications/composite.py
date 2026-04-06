import asyncio
from agents.models import Opportunity
from notifications.base import Notifier


class CompositeNotifier(Notifier):
    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    async def send(self, opportunity: Opportunity) -> None:
        if not self.notifiers:
            return
        # Send concurrently
        await asyncio.gather(
            *(n.send(opportunity) for n in self.notifiers), return_exceptions=True
        )

    async def send_text(self, message: str) -> None:
        if not self.notifiers:
            return
        await asyncio.gather(
            *(n.send_text(message) for n in self.notifiers),
            return_exceptions=True,
        )
