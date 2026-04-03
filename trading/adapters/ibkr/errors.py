from broker.errors import (
    BrokerError, InsufficientFunds, InvalidSymbol, MarketClosed,
    OrderRejected, RateLimitExceeded,
)


def map_ib_error(code: int, message: str) -> BrokerError:
    msg_lower = message.lower()

    if "no security definition" in msg_lower:
        return InvalidSymbol(message, code)

    if "max rate of messages" in msg_lower:
        return RateLimitExceeded(message, code)

    if code == 201:
        if "insufficient" in msg_lower or "margin" in msg_lower:
            return InsufficientFunds(message, code)
        if "market is closed" in msg_lower or "outside trading hours" in msg_lower:
            return MarketClosed(message, code)
        return OrderRejected(message, code)

    return BrokerError(message, code)
