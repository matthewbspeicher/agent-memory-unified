"""Circuit breaker for risk data providers.

Provides resilience for external risk data sources (pricing APIs, VaR calculators, etc.)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout_seconds: float = 60.0  # Time before trying half-open
    half_open_max_calls: int = 3  # Max calls in half-open state


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: datetime | None = None
    last_state_change: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class RiskProviderCircuitBreaker:
    """
    Circuit breaker for risk data providers.

    States:
    - CLOSED: Normal operation, track failures
    - OPEN: Provider failing, reject calls, wait for timeout
    - HALF_OPEN: Test if provider recovered
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.name = name
        self._config = config or CircuitBreakerConfig()
        self._metrics = CircuitBreakerMetrics()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._metrics.state

    @property
    def is_available(self) -> bool:
        """Check if provider can be called."""
        if self._metrics.state == CircuitState.CLOSED:
            return True

        if self._metrics.state == CircuitState.OPEN:
            # Check if timeout has passed to transition to half-open
            if self._metrics.last_failure_time:
                elapsed = datetime.now(timezone.utc) - self._metrics.last_failure_time
                if elapsed.total_seconds() >= self._config.timeout_seconds:
                    return True  # Will transition on next call
            return False

        # HALF_OPEN - allow limited calls
        return True

    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute function with circuit breaker protection.

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        async with self._lock:
            if not self.is_available:
                raise CircuitBreakerOpenError(
                    f"Provider {self.name} circuit is {self._metrics.state.value}"
                )

            # Transition to half-open if needed
            if self._metrics.state == CircuitState.OPEN:
                self._metrics.state = CircuitState.HALF_OPEN
                self._metrics.success_count = 0
                logger.info(
                    f"RiskProviderCircuitBreaker: {self.name} transitioning to HALF_OPEN"
                )

        try:
            result = (
                await func(*args, **kwargs)
                if asyncio.iscoroutinefunction(func)
                else func(*args, **kwargs)
            )
            await self._record_success()
            return result
        except Exception:
            await self._record_failure()
            raise

    async def _record_success(self) -> None:
        async with self._lock:
            self._metrics.failure_count = 0
            self._metrics.last_failure_time = None

            if self._metrics.state == CircuitState.HALF_OPEN:
                self._metrics.success_count += 1
                if self._metrics.success_count >= self._config.success_threshold:
                    self._metrics.state = CircuitState.CLOSED
                    self._metrics.last_state_change = datetime.now(timezone.utc)
                    logger.info(
                        f"RiskProviderCircuitBreaker: {self.name} circuit CLOSED"
                    )

    async def _record_failure(self) -> None:
        async with self._lock:
            self._metrics.failure_count += 1
            self._metrics.last_failure_time = datetime.now(timezone.utc)

            if self._metrics.state == CircuitState.HALF_OPEN:
                self._metrics.state = CircuitState.OPEN
                self._metrics.last_state_change = datetime.now(timezone.utc)
                logger.warning(
                    f"RiskProviderCircuitBreaker: {self.name} circuit OPEN (half-open failure)"
                )
            elif self._metrics.failure_count >= self._config.failure_threshold:
                self._metrics.state = CircuitState.OPEN
                self._metrics.last_state_change = datetime.now(timezone.utc)
                logger.warning(
                    f"RiskProviderCircuitBreaker: {self.name} circuit OPEN after {self._metrics.failure_count} failures"
                )

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "provider": self.name,
            "state": self._metrics.state.value,
            "failure_count": self._metrics.failure_count,
            "success_count": self._metrics.success_count,
            "last_failure": self._metrics.last_failure_time.isoformat()
            if self._metrics.last_failure_time
            else None,
            "last_state_change": self._metrics.last_state_change.isoformat(),
        }

    async def reset(self) -> None:
        """Manually reset circuit breaker."""
        async with self._lock:
            self._metrics = CircuitBreakerMetrics()
            logger.info(f"RiskProviderCircuitBreaker: {self.name} manually reset")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


class RiskProviderCircuitBreakerManager:
    """Manage circuit breakers for multiple risk providers."""

    def __init__(self) -> None:
        self._breakers: dict[str, RiskProviderCircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> RiskProviderCircuitBreaker:
        """Get existing or create new circuit breaker."""
        if name not in self._breakers:
            self._breakers[name] = RiskProviderCircuitBreaker(name, config)
        return self._breakers[name]

    def get_all_status(self) -> list[dict[str, Any]]:
        """Get status of all circuit breakers."""
        return [cb.get_status() for cb in self._breakers.values()]

    async def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for cb in self._breakers.values():
            await cb.reset()
        logger.info("RiskProviderCircuitBreakerManager: all breakers reset")
