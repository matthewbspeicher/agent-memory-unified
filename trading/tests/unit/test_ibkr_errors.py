import pytest
from adapters.ibkr.errors import map_ib_error
from broker.errors import (
    InsufficientFunds, InvalidSymbol, MarketClosed,
    OrderRejected, RateLimitExceeded, BrokerError,
)


class TestMapIBError:
    def test_insufficient_funds(self):
        err = map_ib_error(201, "Order rejected - insufficient margin")
        assert isinstance(err, InsufficientFunds)

    def test_invalid_symbol(self):
        err = map_ib_error(200, "No security definition has been found")
        assert isinstance(err, InvalidSymbol)

    def test_market_closed(self):
        err = map_ib_error(201, "Order rejected - market is closed")
        assert isinstance(err, MarketClosed)

    def test_rate_limit(self):
        err = map_ib_error(100, "Max rate of messages per second has been exceeded")
        assert isinstance(err, RateLimitExceeded)

    def test_order_rejected_generic(self):
        err = map_ib_error(201, "Order rejected - some other reason")
        assert isinstance(err, OrderRejected)

    def test_unknown_error(self):
        err = map_ib_error(9999, "Something unexpected happened")
        assert isinstance(err, BrokerError)
        assert err.code == 9999
