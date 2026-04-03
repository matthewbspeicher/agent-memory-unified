"""Unit tests for broker fee models (Fidelity and IBKR)."""
import pytest
import aiosqlite
from decimal import Decimal

from broker.models import (
    AssetType,
    FidelityFeeModel,
    IBKRFeeModel,
    MarketOrder,
    OrderSide,
    Symbol,
    ZeroFeeModel,
)
from broker.paper import PaperBroker
from storage.paper import PaperStore

from tests.unit.test_broker.test_paper import MockBroker

AAPL = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
AAPL_OPT = Symbol(ticker="AAPL", asset_type=AssetType.OPTION)


# ---------------------------------------------------------------------------
# ZeroFeeModel
# ---------------------------------------------------------------------------

def test_zero_fee_model():
    model = ZeroFeeModel()
    order = MarketOrder(symbol=AAPL, side=OrderSide.BUY, quantity=Decimal("100"), account_id="X")
    assert model.calculate(order, Decimal("150")) == Decimal("0")


# ---------------------------------------------------------------------------
# FidelityFeeModel
# ---------------------------------------------------------------------------

class TestFidelityFeeModel:
    def setup_method(self):
        self.model = FidelityFeeModel()

    def test_stock_buy_no_commission(self):
        order = MarketOrder(symbol=AAPL, side=OrderSide.BUY, quantity=Decimal("10"), account_id="X")
        fee = self.model.calculate(order, Decimal("150.00"))
        assert fee == Decimal("0.00")

    def test_stock_sell_sec_fee(self):
        # Notional = 10 * 150 = 1500
        # SEC fee = 1500 * 0.0000278 = 0.0417 -> rounds to 0.04
        order = MarketOrder(symbol=AAPL, side=OrderSide.SELL, quantity=Decimal("10"), account_id="X")
        fee = self.model.calculate(order, Decimal("150.00"))
        expected = (Decimal("10") * Decimal("150.00") * Decimal("0.0000278")).quantize(Decimal("0.01"))
        assert fee == expected

    def test_stock_sell_sec_fee_minimum(self):
        # Very small trade — notional 1.0, SEC fee = 0.0000278 < 0.01 min
        order = MarketOrder(symbol=AAPL, side=OrderSide.SELL, quantity=Decimal("1"), account_id="X")
        fee = self.model.calculate(order, Decimal("1.00"))
        assert fee == Decimal("0.01")

    def test_option_buy_per_contract(self):
        order = MarketOrder(symbol=AAPL_OPT, side=OrderSide.BUY, quantity=Decimal("5"), account_id="X")
        fee = self.model.calculate(order, Decimal("3.00"))
        assert fee == Decimal("3.25")  # 5 * 0.65

    def test_option_sell_per_contract_plus_sec(self):
        order = MarketOrder(symbol=AAPL_OPT, side=OrderSide.SELL, quantity=Decimal("2"), account_id="X")
        fill = Decimal("5.00")
        # commission = 2 * 0.65 + SEC(2 * 5 = 10, min 0.01)
        contracts_fee = Decimal("2") * Decimal("0.65")
        sec = max(Decimal("0.01"), Decimal("10") * Decimal("0.0000278"))
        expected = (contracts_fee + sec).quantize(Decimal("0.01"))
        fee = self.model.calculate(order, fill)
        assert fee == expected


# ---------------------------------------------------------------------------
# IBKRFeeModel
# ---------------------------------------------------------------------------

class TestIBKRFeeModel:
    def setup_method(self):
        self.model = IBKRFeeModel()

    def test_stock_buy_small_order_min_applied(self):
        # 10 shares * 0.0035 = 0.035 < 0.35 min -> 0.35
        order = MarketOrder(symbol=AAPL, side=OrderSide.BUY, quantity=Decimal("10"), account_id="X")
        fee = self.model.calculate(order, Decimal("100.00"))
        assert fee == Decimal("0.3500")

    def test_stock_buy_normal_order(self):
        # 200 shares * 0.0035 = 0.70 > 0.35 min; cap = 200 * 100 * 0.01 = 200 -> not applied
        order = MarketOrder(symbol=AAPL, side=OrderSide.BUY, quantity=Decimal("200"), account_id="X")
        fee = self.model.calculate(order, Decimal("100.00"))
        assert fee == Decimal("0.7000")

    def test_stock_buy_cap_applied(self):
        # 1000 shares * 0.0035 = 3.50; notional = 1000 * 0.01 = 10; cap is 1% of notional
        # Here with low price: 1000 shares @ 0.05 = 50 notional, cap = 0.50, raw = 3.50 -> 0.50
        order = MarketOrder(symbol=AAPL, side=OrderSide.BUY, quantity=Decimal("1000"), account_id="X")
        fee = self.model.calculate(order, Decimal("0.05"))
        # notional = 50, cap = 0.50, raw = 3.50, capped = 0.50, min = 0.35 -> 0.50
        assert fee == Decimal("0.5000")

    def test_stock_sell_includes_finra_taf(self):
        # 100 shares * 0.0035 = 0.35 (min), FINRA = 100 * 0.000166 = 0.0166
        order = MarketOrder(symbol=AAPL, side=OrderSide.SELL, quantity=Decimal("100"), account_id="X")
        fee = self.model.calculate(order, Decimal("50.00"))
        commission = Decimal("0.35")
        finra = Decimal("100") * Decimal("0.000166")
        expected = (commission + finra).quantize(Decimal("0.0001"))
        assert fee == expected

    def test_stock_sell_finra_taf_max(self):
        # 100000 shares * 0.000166 = 16.6 > 8.30 max
        order = MarketOrder(symbol=AAPL, side=OrderSide.SELL, quantity=Decimal("100000"), account_id="X")
        fee = self.model.calculate(order, Decimal("10.00"))
        assert fee >= Decimal("8.30")  # FINRA capped at 8.30

    def test_option_buy_minimum(self):
        # 1 contract * 0.65 = 0.65 < 1.00 min -> 1.00
        order = MarketOrder(symbol=AAPL_OPT, side=OrderSide.BUY, quantity=Decimal("1"), account_id="X")
        fee = self.model.calculate(order, Decimal("2.00"))
        assert fee == Decimal("1.0000")

    def test_option_buy_above_minimum(self):
        # 3 contracts * 0.65 = 1.95 > 1.00 min -> 1.95
        order = MarketOrder(symbol=AAPL_OPT, side=OrderSide.BUY, quantity=Decimal("3"), account_id="X")
        fee = self.model.calculate(order, Decimal("5.00"))
        assert fee == Decimal("1.9500")


# ---------------------------------------------------------------------------
# Integration: PaperBroker deducts commission from cash
# ---------------------------------------------------------------------------

@pytest.fixture
async def paper_store_with_balance():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    store = PaperStore(db)
    await store.init_tables()
    yield store
    await db.close()


async def test_paper_broker_deducts_ibkr_fee(paper_store_with_balance):
    fee_model = IBKRFeeModel()
    broker = PaperBroker(MockBroker(), paper_store_with_balance, fee_model=fee_model)

    order = MarketOrder(
        symbol=AAPL,
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        account_id="PAPER",
    )
    result = await broker.orders.place_order("PAPER", order)

    # MockBroker returns ask=150.1 for buys
    fill_price = Decimal("150.1")
    expected_commission = fee_model.calculate(order, fill_price)
    expected_cash = Decimal("100000.0") - (Decimal("100") * fill_price) - expected_commission

    bal = await broker.account.get_balances("PAPER")
    assert bal.cash == expected_cash
    assert result.commission == expected_commission


async def test_paper_broker_deducts_fidelity_fee_on_sell(paper_store_with_balance):
    fee_model = FidelityFeeModel()
    broker = PaperBroker(MockBroker(), paper_store_with_balance, fee_model=fee_model)

    # First buy to establish a position
    await broker.orders.place_order(
        "PAPER",
        MarketOrder(symbol=AAPL, side=OrderSide.BUY, quantity=Decimal("10"), account_id="PAPER"),
    )
    bal_after_buy = await broker.account.get_balances("PAPER")

    # Now sell; Fidelity charges SEC fee on sells
    sell_order = MarketOrder(
        symbol=AAPL, side=OrderSide.SELL, quantity=Decimal("10"), account_id="PAPER"
    )
    # MockBroker returns bid=150.0 for sells
    fill_price = Decimal("150.0")
    expected_fee = fee_model.calculate(sell_order, fill_price)
    assert expected_fee > Decimal("0")  # SEC fee must be charged

    await broker.orders.place_order("PAPER", sell_order)
    bal_after_sell = await broker.account.get_balances("PAPER")

    # Cash after sell = cash_before + proceeds - fee
    expected_cash = bal_after_buy.cash + (Decimal("10") * fill_price) - expected_fee
    assert bal_after_sell.cash == expected_cash
