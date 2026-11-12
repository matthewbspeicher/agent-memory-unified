from decimal import Decimal as D
from dataclasses import replace
import pytest
from broker.models import (
    MarketOrder,
    Symbol,
    OrderSide,
    AssetType,
    IBKRFeeModel,
    FidelityFeeModel,
    ZeroFeeModel,
    BinanceFeeModel,
    FeeModel,
)


def order(side=OrderSide.BUY, asset=AssetType.STOCK):
    return MarketOrder(Symbol("TEST", asset), side, D(1), "PAPER")


@pytest.mark.parametrize(
    "model,side,asset,fragments",
    [
        (
            IBKRFeeModel(),
            OrderSide.BUY,
            AssetType.STOCK,
            [(1, 100), (2, 99), (197, 98)],
        ),
        (
            IBKRFeeModel(),
            OrderSide.SELL,
            AssetType.STOCK,
            [(1, 100), (2, 99), (197, 98)],
        ),
        (IBKRFeeModel(), OrderSide.BUY, AssetType.OPTION, [(1, 2), (1, 3), (1, 4)]),
        (FidelityFeeModel(), OrderSide.SELL, AssetType.STOCK, [(1, 1), (1, 2), (1, 3)]),
        (
            FidelityFeeModel(),
            OrderSide.SELL,
            AssetType.OPTION,
            [(1, 2), (1, 3), (1, 4)],
        ),
    ],
)
def test_per_order_fee_equals_single_calculation_on_actual_fills(
    model, side, asset, fragments
):
    trade = order(side, asset)
    quantity = notional = paid = D(0)
    for q, p in fragments:
        fragment = replace(trade, quantity=D(q))
        charge = model.calculate_incremental(
            fragment,
            D(p),
            filled_quantity=quantity,
            filled_notional=notional,
            commission_paid=paid,
        )
        assert charge >= 0
        quantity += D(q)
        notional += D(q) * D(p)
        paid += charge
    assert paid == model.calculate(
        replace(trade, quantity=quantity), notional / quantity
    )


def test_ibkr_minimum_once_and_top_up_above_minimum():
    model = IBKRFeeModel()
    assert model.calculate_incremental(order(), D(100)) == D(".3500")
    assert (
        model.calculate_incremental(
            order(),
            D(100),
            filled_quantity=D(1),
            filled_notional=D(100),
            commission_paid=D(".35"),
        )
        == 0
    )
    assert model.calculate_incremental(
        replace(order(), quantity=D(199)),
        D(100),
        filled_quantity=D(1),
        filled_notional=D(100),
        commission_paid=D(".35"),
    ) == D(".35")


def test_custom_and_percentage_models_retain_per_fill_semantics():
    class Fixed(FeeModel):
        def calculate(self, order, fill_price):
            return D(".5")

    for model in [Fixed(), BinanceFeeModel(), ZeroFeeModel()]:
        expected = model.calculate(order(), D(100))
        assert (
            model.calculate_incremental(
                order(),
                D(100),
                filled_quantity=D(1),
                filled_notional=D(100),
                commission_paid=expected,
            )
            == expected
        )


@pytest.mark.parametrize("paid", [D("NaN"), D("Infinity"), D(-1), D(1)])
def test_invalid_or_overpaid_cumulative_evidence_fails_closed(paid):
    with pytest.raises(ValueError):
        IBKRFeeModel().calculate_incremental(
            order(),
            D(100),
            filled_quantity=D(1),
            filled_notional=D(100),
            commission_paid=paid,
        )
