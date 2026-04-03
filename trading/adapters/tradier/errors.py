from __future__ import annotations


class TradierAPIError(Exception):
    """Base error for Tradier API failures."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Tradier API error {code}: {message}")


class TradierInsufficientFunds(TradierAPIError):
    """Insufficient funds for the requested order."""


class TradierOrderRejected(TradierAPIError):
    """Order rejected by Tradier."""


class TradierRateLimited(TradierAPIError):
    """429 Too Many Requests."""


class TradierInvalidSymbol(TradierAPIError):
    """Invalid or unknown symbol."""
