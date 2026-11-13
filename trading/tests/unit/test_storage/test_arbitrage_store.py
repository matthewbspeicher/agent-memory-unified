"""ArbStore returns the orders it was given."""

from datetime import date
from decimal import Decimal

import aiosqlite
import pytest

from broker.models import (
    TIF,
    AssetType,
    LimitOrder,
    MarketOrder,
    OptionRight,
    OrderSide,
    StopLimitOrder,
    StopOrder,
    Symbol,
    TrailingStopOrder,
)
from execution.models import ArbLeg, ArbTrade
from storage.arbitrage import ArbStore
from storage.db import init_db

PREDICTION = Symbol("KX-1", AssetType.PREDICTION)
OPTION = Symbol(
    "AAPL",
    AssetType.OPTION,
    expiry=date(2027, 1, 15),
    strike=Decimal("187.5"),
    right=OptionRight.CALL,
    multiplier=100,
)
TERMS = (OrderSide.SELL, Decimal("5"), "PAPER", TIF.GTC, "signal-1")
ORDERS = [
    MarketOrder(PREDICTION, *TERMS),
    LimitOrder(PREDICTION, *TERMS, limit_price=Decimal("0.57")),
    StopOrder(OPTION, *TERMS, stop_price=Decimal("1.25")),
    StopLimitOrder(
        OPTION, *TERMS, stop_price=Decimal("1.25"), limit_price=Decimal("1.2")
    ),
    TrailingStopOrder(PREDICTION, *TERMS, trail_percent=Decimal("2.5")),
]


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield ArbStore(db)
    await db.close()


async def save(store, order, other=ORDERS[0]):
    await store.save_trade(
        ArbTrade(
            id="arb-1",
            symbol_a="KX-1",
            symbol_b="POLY-1",
            leg_a=ArbLeg("kalshi_paper", order),
            leg_b=ArbLeg("polymarket_paper", other),
            expected_profit_bps=120,
        )
    )


@pytest.mark.parametrize("order", ORDERS, ids=lambda order: type(order).__name__)
async def test_a_stored_order_is_read_back_as_it_was_given(store, order):
    await save(store, order)
    read = (await store.get_trade("arb-1")).leg_a.order
    assert (type(read), read) == (type(order), order)


async def test_an_order_with_unrecognised_terms_is_refused(store):
    await save(store, ORDERS[1])
    await store._db.execute(
        "UPDATE arb_legs SET order_data = json_set(order_data, '$.peg', '1')"
        " WHERE leg_name = 'leg_a'"
    )
    with pytest.raises(ValueError, match="arb-1.*leg_a"):
        await store.get_trade("arb-1")
