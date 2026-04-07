from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class CircuitOpenError(Exception):
    """Raised when a call is attempted on an open circuit."""


class ProviderCircuitBreaker:
    """Three-state circuit breaker: closed -> open -> half_open -> closed."""

    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures: int = 0
        self.state: str = "closed"
        self.last_failure_time: datetime | None = None

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        if self.state == "open":
            if self._should_attempt_reset():
                return await self._half_open_probe(func)
            raise CircuitOpenError(f"Circuit open, retry after {self.reset_timeout}s")

        try:
            result = await func()
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
        return elapsed >= self.reset_timeout

    async def _half_open_probe(self, func: Callable[[], Awaitable[T]]) -> T:
        try:
            result = await func()
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self.failures = 0
        self.state = "closed"

    def _on_failure(self) -> None:
        self.failures += 1
        self.last_failure_time = datetime.now(timezone.utc)
        if self.failures >= self.failure_threshold:
            self.state = "open"
