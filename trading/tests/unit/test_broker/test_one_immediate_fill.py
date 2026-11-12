"""Every paper venue fills a marketable order through one implementation."""

import pytest

from adapters.kalshi.paper import KalshiPaperOrderManager
from adapters.paper.broker import PaperOrderManager as SimulatedOrderManager
from adapters.polymarket.paper import PolymarketPaperOrderManager
from broker.paper import ImmediatePaperOrderManager, PaperOrderManager

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


@pytest.mark.parametrize("manager", VENUES)
def test_venue_supplies_its_own_slippage(manager):
    assert manager._slipped_price is not ImmediatePaperOrderManager._slipped_price
