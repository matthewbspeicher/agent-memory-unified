"""Unit tests for execution cost math helpers."""
from __future__ import annotations

from decimal import Decimal

import pytest

from execution.costs import decision_price, order_type_label, slippage_bps, spread_bps


class TestDecisionPrice:
    def test_midpoint_when_both_bid_ask(self):
        result = decision_price(Decimal("99"), Decimal("101"), Decimal("100"))
        assert result == Decimal("100")

    def test_falls_back_to_last_when_no_bid_ask(self):
        result = decision_price(None, None, Decimal("150"))
        assert result == Decimal("150")

    def test_bid_only_returns_bid(self):
        result = decision_price(Decimal("99"), None, None)
        assert result == Decimal("99")

    def test_ask_only_returns_ask(self):
        result = decision_price(None, Decimal("101"), None)
        assert result == Decimal("101")

    def test_all_none_returns_none(self):
        assert decision_price(None, None, None) is None

    def test_prefers_mid_over_last(self):
        result = decision_price(Decimal("98"), Decimal("102"), Decimal("99"))
        assert result == Decimal("100")


class TestSpreadBps:
    def test_normal_spread(self):
        bid = Decimal("99")
        ask = Decimal("101")
        mid = Decimal("100")
        result = spread_bps(bid, ask, mid)
        assert result == pytest.approx(200.0)

    def test_tight_spread(self):
        bid = Decimal("100.00")
        ask = Decimal("100.01")
        mid = Decimal("100.005")
        result = spread_bps(bid, ask, mid)
        assert result == pytest.approx(1.0, rel=1e-3)

    def test_no_bid_returns_none(self):
        assert spread_bps(None, Decimal("101"), Decimal("100")) is None

    def test_no_ask_returns_none(self):
        assert spread_bps(Decimal("99"), None, Decimal("100")) is None

    def test_no_mid_returns_none(self):
        assert spread_bps(Decimal("99"), Decimal("101"), None) is None

    def test_zero_mid_returns_none(self):
        assert spread_bps(Decimal("0"), Decimal("0"), Decimal("0")) is None


class TestSlippageBps:
    def test_buy_positive_slippage(self):
        # Filled above decision — worse for buyer
        result = slippage_bps(Decimal("101"), Decimal("100"), "BUY")
        assert result == pytest.approx(100.0)

    def test_buy_negative_slippage(self):
        # Filled below decision — better for buyer
        result = slippage_bps(Decimal("99"), Decimal("100"), "BUY")
        assert result == pytest.approx(-100.0)

    def test_sell_positive_slippage(self):
        # Filled below decision — worse for seller
        result = slippage_bps(Decimal("99"), Decimal("100"), "SELL")
        assert result == pytest.approx(100.0)

    def test_sell_negative_slippage(self):
        # Filled above decision — better for seller
        result = slippage_bps(Decimal("101"), Decimal("100"), "SELL")
        assert result == pytest.approx(-100.0)

    def test_no_fill_returns_none(self):
        assert slippage_bps(None, Decimal("100"), "BUY") is None

    def test_no_decision_returns_none(self):
        assert slippage_bps(Decimal("100"), None, "BUY") is None

    def test_zero_decision_returns_none(self):
        assert slippage_bps(Decimal("100"), Decimal("0"), "BUY") is None

    def test_side_case_insensitive(self):
        result_lower = slippage_bps(Decimal("101"), Decimal("100"), "buy")
        result_upper = slippage_bps(Decimal("101"), Decimal("100"), "BUY")
        assert result_lower == result_upper

    def test_zero_slippage(self):
        result = slippage_bps(Decimal("100"), Decimal("100"), "BUY")
        assert result == pytest.approx(0.0)


class TestOrderTypeLabel:
    def test_market_order(self):
        class MarketOrder:
            pass
        assert order_type_label(MarketOrder()) == "market"

    def test_limit_order(self):
        class LimitOrder:
            pass
        assert order_type_label(LimitOrder()) == "limit"

    def test_stop_order(self):
        class StopOrder:
            pass
        assert order_type_label(StopOrder()) == "stop"

    def test_none_returns_unknown(self):
        assert order_type_label(None) == "unknown"

    def test_arbitrary_class(self):
        class MyCustomType:
            pass
        assert order_type_label(MyCustomType()) == "mycustomtype"
