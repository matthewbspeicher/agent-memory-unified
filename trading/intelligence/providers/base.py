from __future__ import annotations

import abc
from intelligence.models import IntelReport


class BaseIntelProvider(abc.ABC):
    """Abstract base for all intelligence providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'on_chain', 'sentiment', 'anomaly')."""

    @abc.abstractmethod
    async def analyze(self, symbol: str) -> IntelReport | None:
        """Analyze the given symbol and return an IntelReport, or None if unavailable."""
