from __future__ import annotations
from decimal import Decimal


from broker.models import Quote, Symbol


async def test_update_quote_cache_makes_quote_available():
    from data.bus import DataBus

    bus = DataBus.__new__(DataBus)
    bus._quote_cache = {}

    symbol = Symbol(ticker="AAPL")
    quote = Quote(symbol=symbol, bid=Decimal("150.0"), ask=Decimal("150.5"))

    await bus.update_quote_cache(symbol, quote)

    assert "AAPL" in bus._quote_cache
    assert bus._quote_cache["AAPL"].bid == Decimal("150.0")


async def test_invalidate_quote_cache_removes_entries():
    from data.bus import DataBus

    bus = DataBus.__new__(DataBus)
    symbol = Symbol(ticker="AAPL")
    bus._quote_cache = {"AAPL": Quote(symbol=symbol, bid=Decimal("150.0"))}

    bus.invalidate_quote_cache(["AAPL"])

    assert "AAPL" not in bus._quote_cache


async def test_invalidate_nonexistent_symbol_no_error():
    from data.bus import DataBus

    bus = DataBus.__new__(DataBus)
    bus._quote_cache = {}

    # Should not raise
    bus.invalidate_quote_cache(["NONEXISTENT"])
