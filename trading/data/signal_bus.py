from datetime import datetime, timezone
import logging
from typing import Callable, Awaitable
from agents.models import AgentSignal

logger = logging.getLogger(__name__)

MAX_SIGNALS = 1000


class SignalBus:
    def __init__(self):
        self._signals: list[AgentSignal] = []
        self._subscribers: list[Callable[[AgentSignal], Awaitable[None]]] = []

    def _prune_expired(self) -> None:
        now = datetime.now(timezone.utc)
        self._signals = [s for s in self._signals if s.expires_at > now]

    async def publish(self, signal: AgentSignal) -> None:
        self._prune_expired()
        self._signals.append(signal)
        if len(self._signals) > MAX_SIGNALS:
            self._signals = self._signals[-MAX_SIGNALS:]
        for sub in self._subscribers:
            try:
                await sub(signal)
            except Exception as e:
                logger.error(
                    "Error in signal subscriber for signal_type=%s source_agent=%s: %s",
                    signal.signal_type, signal.source_agent, e,
                )

    def subscribe(self, callback: Callable[[AgentSignal], Awaitable[None]]) -> None:
        self._subscribers.append(callback)

    def query(self, signal_type: str | None = None, target_agent: str | None = None) -> list[AgentSignal]:
        self._prune_expired()
        results = self._signals
        if signal_type:
            results = [s for s in results if s.signal_type == signal_type]
        if target_agent:
            results = [s for s in results if s.target_agent == target_agent or s.target_agent is None]
        return results
