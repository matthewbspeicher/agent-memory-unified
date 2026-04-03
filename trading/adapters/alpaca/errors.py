from __future__ import annotations


class AlpacaAPIError(Exception):
    """Base error for Alpaca API failures."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Alpaca API error {code}: {message}")


class AlpacaInsufficientFunds(AlpacaAPIError):
    """Insufficient buying power for the requested order."""


class AlpacaOrderRejected(AlpacaAPIError):
    """Order rejected by Alpaca (invalid params, symbol halted, etc.)."""


class AlpacaForbidden(AlpacaAPIError):
    """Authentication or data feed tier mismatch (wrong feed for plan)."""


class AlpacaRateLimited(AlpacaAPIError):
    """429 Too Many Requests — rate limit exceeded."""


class AlpacaAssetNotTradeable(AlpacaAPIError):
    """Symbol is not tradeable or is halted."""
