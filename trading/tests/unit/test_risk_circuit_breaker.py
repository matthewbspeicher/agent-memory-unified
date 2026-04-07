"""Unit tests for RiskProviderCircuitBreaker."""

import asyncio
import pytest

from trading.risk.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    RiskProviderCircuitBreaker,
    RiskProviderCircuitBreakerManager,
)


class TestRiskProviderCircuitBreaker:
    """Tests for circuit breaker."""

    @pytest.mark.asyncio
    async def test_closed_state_initially(self):
        """Test circuit starts in closed state."""
        cb = RiskProviderCircuitBreaker("test_provider")

        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True

    @pytest.mark.asyncio
    async def test_successful_call_keeps_closed(self):
        """Test successful call keeps circuit closed."""
        cb = RiskProviderCircuitBreaker("test_provider")

        async def success_func():
            return "success"

        result = await cb.call(success_func)

        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb._metrics.failure_count == 0

    @pytest.mark.asyncio
    async def test_failure_opens_circuit(self):
        """Test failures open circuit after threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = RiskProviderCircuitBreaker("test_provider", config)

        async def fail_func():
            raise ValueError("Provider failed")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail_func)

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_calls(self):
        """Test open circuit rejects calls."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0.1)
        cb = RiskProviderCircuitBreaker("test_provider", config)

        async def fail_func():
            raise ValueError("Provider failed")

        # First failure opens circuit
        with pytest.raises(ValueError):
            await cb.call(fail_func)

        assert cb.state == CircuitState.OPEN

        # Second call should be rejected immediately
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(fail_func)

    @pytest.mark.asyncio
    async def test_half_open_transition(self):
        """Test circuit transitions to half-open after timeout."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=0.05,  # Very short for test
            success_threshold=2,
        )
        cb = RiskProviderCircuitBreaker("test_provider", config)

        async def fail_func():
            raise ValueError("Provider failed")

        # Open the circuit
        with pytest.raises(ValueError):
            await cb.call(fail_func)

        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.1)

        # Next call should transition to half-open
        async def success_func():
            return "success"

        result = await cb.call(success_func)

        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test manual reset."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = RiskProviderCircuitBreaker("test_provider", config)

        async def fail_func():
            raise ValueError("Provider failed")

        # Open circuit
        with pytest.raises(ValueError):
            await cb.call(fail_func)

        assert cb.state == CircuitState.OPEN

        # Reset
        await cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True


class TestRiskProviderCircuitBreakerManager:
    """Tests for circuit breaker manager."""

    def test_get_or_create(self):
        """Test getting or creating breakers."""
        manager = RiskProviderCircuitBreakerManager()

        cb1 = manager.get_or_create("provider1")
        cb2 = manager.get_or_create("provider1")
        cb3 = manager.get_or_create("provider2")

        assert cb1 is cb2  # Same instance
        assert cb1 is not cb3  # Different provider

    def test_get_all_status(self):
        """Test getting status of all breakers."""
        manager = RiskProviderCircuitBreakerManager()

        manager.get_or_create("provider1")
        manager.get_or_create("provider2")

        status = manager.get_all_status()

        assert len(status) == 2
        assert any(s["provider"] == "provider1" for s in status)
        assert any(s["provider"] == "provider2" for s in status)

    @pytest.mark.asyncio
    async def test_reset_all(self):
        """Test resetting all breakers."""
        manager = RiskProviderCircuitBreakerManager()

        cb1 = manager.get_or_create("provider1")
        cb2 = manager.get_or_create("provider2")

        # Set them to open state
        cb1._metrics.state = CircuitState.OPEN
        cb2._metrics.state = CircuitState.OPEN

        # Reset all
        await manager.reset_all()

        assert cb1.state == CircuitState.CLOSED
        assert cb2.state == CircuitState.CLOSED


class TestCircuitBreakerConfig:
    """Tests for circuit breaker config."""

    def test_defaults(self):
        """Test default config values."""
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout_seconds == 60.0
        assert config.half_open_max_calls == 3

    def test_custom_values(self):
        """Test custom config values."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            timeout_seconds=30.0,
        )

        assert config.failure_threshold == 10
        assert config.success_threshold == 2  # Default
        assert config.timeout_seconds == 30.0
