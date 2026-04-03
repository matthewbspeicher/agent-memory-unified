from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from broker.models import Quote


class BrokerStream(ABC):
    """Abstract base for real-time broker quote streams."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def subscribe(self, symbols: list[str]) -> None: ...

    @abstractmethod
    async def unsubscribe(self, symbols: list[str]) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def on_quote(self, callback: Callable[[str, Quote], Awaitable[None]]) -> None:
        """Register an async callback invoked on each quote: (symbol, quote) → awaitable."""

    @abstractmethod
    def on_disconnected(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked when the stream disconnects."""
