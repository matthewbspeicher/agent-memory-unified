from __future__ import annotations
from abc import ABC, abstractmethod

from agents.models import Opportunity


class Notifier(ABC):
    @abstractmethod
    async def send(self, opportunity: Opportunity) -> None: ...

    async def send_text(self, message: str) -> None:
        """Send a plain text alert. Default: no-op (subclasses override)."""
