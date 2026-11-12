"""Whether a paper order rests is a typed decision, not a matched message."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from broker.models import (
    LimitOrder,
    MarketOrder,
    OrderSide,
    OrderStatus,
    Quote,
    StopLimitOrder,
    StopOrder,
    Symbol,
    TIF,
)
from broker.paper import PaperOrderManager, executable_paper_price
from broker.paper_matching import PaperOrderMustRest
from storage.paper import PaperStore

AAPL = Symbol("AAPL")


def quote(bid="99", ask="101"):
    return Quote(AAPL, Decimal(bid), Decimal(ask), Decimal("100"), 0, datetime.now(timezone.utc))


def test_marketable_limit_prices_at_the_quote():
    order = LimitOrder(AAPL, OrderSide.BUY, Decimal("1"), "PAPER", limit_price=Decimal("102"))
    assert executable_paper_price(order, quote()) == (Decimal("101"), Decimal("102"))


def test_unmarketable_limit_must_rest_untriggered():
    order = LimitOrder(AAPL, OrderSide.BUY, Decimal("1"), "PAPER", limit_price=Decimal("90"))
    with pytest.raises(PaperOrderMustRest, match="Limit is not marketable") as raised:
        executable_paper_price(order, quote())
    assert raised.value.stop_triggered is False


def test_untriggered_stop_must_rest_untriggered():
    order = StopOrder(AAPL, OrderSide.BUY, Decimal("1"), "PAPER", stop_price=Decimal("110"))
    with pytest.raises(PaperOrderMustRest, match="Stop is not triggered") as raised:
        executable_paper_price(order, quote())
    assert raised.value.stop_triggered is False


def test_triggered_stop_limit_that_is_not_marketable_rests_as_triggered():
    order = StopLimitOrder(
        AAPL, OrderSide.BUY, Decimal("1"), "PAPER",
        stop_price=Decimal("100"), limit_price=Decimal("100.5"),
    )
    with pytest.raises(PaperOrderMustRest, match="Limit is not marketable") as raised:
        executable_paper_price(order, quote())
    assert raised.value.stop_triggered is True


def test_other_refusals_are_definite_rejections():
    order = MarketOrder(AAPL, OrderSide.BUY, Decimal("1"), "PAPER")
    with pytest.raises(ValueError) as raised:
        executable_paper_price(order, None)
    assert not isinstance(raised.value, PaperOrderMustRest)


# --- The order manager acting on the decision, against a real ledger ---

@pytest.fixture
async def manager(tmp_path):
    async with aiosqlite.connect(tmp_path / "ledger.db") as application:
        application.row_factory = aiosqlite.Row
        store = PaperStore(application)
        await store.init_tables()
        market_data = SimpleNamespace(
            get_quote=AsyncMock(side_effect=lambda symbol: quote()),
            get_order_book=AsyncMock(return_value={}),
        )
        try:
            yield PaperOrderManager(market_data, store, max_slippage=Decimal("0"))
        finally:
            await store.close()


def resting_limit(tif):
    return LimitOrder(
        AAPL, OrderSide.BUY, Decimal("1"), "PAPER", tif, limit_price=Decimal("90")
    )


@pytest.mark.parametrize("tif", [TIF.DAY, TIF.GTC])
async def test_unmarketable_limit_rests_when_its_duration_allows(manager, tif):
    result = await manager.place_order("PAPER", resting_limit(tif))
    assert result.status == OrderStatus.SUBMITTED
    assert await manager.store.open_orders_by_arrival("PAPER") == [
        (result.order_id, False)
    ]


async def test_unmarketable_immediate_or_cancel_limit_is_rejected(manager):
    result = await manager.place_order("PAPER", resting_limit(TIF.IOC))
    assert result.status == OrderStatus.REJECTED
    assert "Limit is not marketable" in result.message
    assert await manager.store.open_order_ids("PAPER") == []


async def test_untriggered_stop_rests_untriggered(manager):
    order = StopOrder(
        AAPL, OrderSide.BUY, Decimal("1"), "PAPER", stop_price=Decimal("110")
    )
    result = await manager.place_order("PAPER", order)
    assert await manager.store.open_orders_by_arrival("PAPER") == [
        (result.order_id, False)
    ]


async def test_stop_limit_hit_at_submission_rests_as_triggered(manager):
    order = StopLimitOrder(
        AAPL,
        OrderSide.BUY,
        Decimal("1"),
        "PAPER",
        stop_price=Decimal("100"),
        limit_price=Decimal("100.5"),
    )
    result = await manager.place_order("PAPER", order)
    assert await manager.store.open_orders_by_arrival("PAPER") == [
        (result.order_id, True)
    ]


async def test_marketable_limit_fills_and_leaves_nothing_resting(manager):
    order = LimitOrder(
        AAPL, OrderSide.BUY, Decimal("1"), "PAPER", limit_price=Decimal("102")
    )
    result = await manager.place_order("PAPER", order)
    assert result.status == OrderStatus.FILLED
    assert await manager.store.open_order_ids("PAPER") == []
