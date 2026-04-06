class BrokerError(Exception):
    """Base exception for all broker errors."""

    def __init__(self, message: str = "", code: int | None = None):
        self.code = code
        super().__init__(message)


class BrokerConnectionError(BrokerError):
    """Failed to connect or lost connection to broker."""


class InvalidSymbol(BrokerError):
    """Symbol could not be resolved by the broker."""


class InsufficientFunds(BrokerError):
    """Account lacks sufficient funds/margin for the order."""


class MarketClosed(BrokerError):
    """Market is closed for the requested instrument."""


class OrderRejected(BrokerError):
    """Broker rejected the order."""

    def __init__(self, reason: str, code: int | None = None):
        self.reason = reason
        super().__init__(reason, code)


class RateLimitExceeded(BrokerError):
    """Too many requests sent to broker."""
