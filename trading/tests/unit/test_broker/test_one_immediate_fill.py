"""Every paper venue fills a marketable order through one implementation."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.kalshi.paper import KalshiPaperOrderManager
from adapters.paper.broker import PaperOrderManager as SimulatedOrderManager
from adapters.polymarket.paper import PolymarketPaperOrderManager
from broker.models import (
    AssetType,
    LimitOrder,
    MarketOrder,
    OrderSide,
    OrderStatus,
    Quote,
    Symbol,
)
from broker.paper import ImmediatePaperOrderManager, PaperOrderManager
from broker.paper_matching import PaperOrderMustRest

VENUES = [
    PaperOrderManager,
    SimulatedOrderManager,
    KalshiPaperOrderManager,
    PolymarketPaperOrderManager,
]


@pytest.mark.parametrize("manager", VENUES)
def test_venue_does_not_reimplement_the_fill(manager):
    assert (
        manager._place_immediate_order
        is ImmediatePaperOrderManager._place_immediate_order
    )


PREDICTION = [
    (KalshiPaperOrderManager, "Kalshi", "KALSHI_PAPER"),
    (PolymarketPaperOrderManager, "Polymarket", "POLYMARKET_PAPER"),
]


def _manager(cls, market_data):
    store = MagicMock()
    store.record_fill = AsyncMock()
    store.save_order = AsyncMock()
    return cls(store, 1, market_data), store


def _limit(account, price="0.50"):
    return LimitOrder(
        Symbol("MKT", AssetType.PREDICTION),
        OrderSide.BUY,
        Decimal("5"),
        account,
        limit_price=Decimal(price),
    )


@pytest.mark.parametrize("cls, venue, account", PREDICTION)
async def test_prediction_venue_refuses_non_limit_orders_by_name(cls, venue, account):
    manager, store = _manager(cls, SimpleNamespace(get_quote=AsyncMock()))
    order = MarketOrder(
        Symbol("MKT", AssetType.PREDICTION), OrderSide.BUY, Decimal("5"), account
    )
    result = await manager._place_immediate_order(account, order)
    assert (result.status, result.message) == (
        OrderStatus.REJECTED,
        f"{venue}PaperBroker only accepts LimitOrder",
    )
    store.record_fill.assert_not_awaited()


@pytest.mark.parametrize("cls, venue, account", PREDICTION)
async def test_prediction_venue_without_market_data_rejects(cls, venue, account):
    manager, store = _manager(cls, None)
    result = await manager._place_immediate_order(account, _limit(account))
    assert (result.status, result.message) == (
        OrderStatus.REJECTED,
        "No market data available for fill simulation",
    )


@pytest.mark.parametrize("cls, venue, account", PREDICTION)
@pytest.mark.parametrize("error", [ValueError("no book"), NotImplementedError("stub")])
async def test_prediction_venue_rejects_on_quote_source_errors(
    cls, venue, account, error
):
    manager, store = _manager(
        cls, SimpleNamespace(get_quote=AsyncMock(side_effect=error))
    )
    result = await manager._place_immediate_order(account, _limit(account))
    assert (result.status, result.message) == (OrderStatus.REJECTED, str(error))
    store.record_fill.assert_not_awaited()


@pytest.mark.parametrize("cls, venue, account", PREDICTION)
async def test_must_rest_from_the_quote_source_is_not_swallowed(cls, venue, account):
    signal = PaperOrderMustRest("resting", stop_triggered=False)
    manager, _ = _manager(cls, SimpleNamespace(get_quote=AsyncMock(side_effect=signal)))
    with pytest.raises(PaperOrderMustRest):
        await manager._place_immediate_order(account, _limit(account))


@pytest.mark.parametrize("cls, venue, account", PREDICTION)
async def test_prediction_fill_slips_one_cent_and_is_capped_by_the_limit(
    cls, venue, account
):
    symbol = Symbol("MKT", AssetType.PREDICTION)
    quote = Quote(symbol, Decimal("0.40"), Decimal("0.495"), Decimal("0.45"))
    manager, store = _manager(
        cls, SimpleNamespace(get_quote=AsyncMock(return_value=quote))
    )
    result = await manager._place_immediate_order(account, _limit(account))
    # ask 0.495 plus one cent is 0.505, capped at the 0.50 limit
    assert (result.status, result.avg_fill_price) == (
        OrderStatus.FILLED,
        Decimal("0.50"),
    )
    assert store.record_fill.call_args.kwargs["commission"] == Decimal("0")
