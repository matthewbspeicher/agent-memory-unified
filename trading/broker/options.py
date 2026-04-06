from decimal import Decimal
from datetime import date
from broker.models import (
    Symbol,
    AssetType,
    OptionRight,
    OrderSide,
    OptionLeg,
    ComboOrder,
)


def _make_option_symbol(
    underlying: Symbol, expiry: date, strike: Decimal, right: OptionRight
) -> Symbol:
    return Symbol(
        ticker=underlying.ticker,
        asset_type=AssetType.OPTION,
        exchange=underlying.exchange,
        currency=underlying.currency,
        expiry=expiry,
        strike=strike,
        right=right,
        multiplier=100,
    )


def build_iron_condor(
    account_id: str,
    underlying: Symbol,
    quantity: Decimal,
    expiry: date,
    short_put_strike: Decimal,
    long_put_strike: Decimal,
    short_call_strike: Decimal,
    long_call_strike: Decimal,
) -> ComboOrder:
    """Builds a short Iron Condor order."""
    legs = [
        OptionLeg(
            symbol=_make_option_symbol(
                underlying, expiry, long_put_strike, OptionRight.PUT
            ),
            side=OrderSide.BUY,
            ratio=1,
        ),
        OptionLeg(
            symbol=_make_option_symbol(
                underlying, expiry, short_put_strike, OptionRight.PUT
            ),
            side=OrderSide.SELL,
            ratio=1,
        ),
        OptionLeg(
            symbol=_make_option_symbol(
                underlying, expiry, short_call_strike, OptionRight.CALL
            ),
            side=OrderSide.SELL,
            ratio=1,
        ),
        OptionLeg(
            symbol=_make_option_symbol(
                underlying, expiry, long_call_strike, OptionRight.CALL
            ),
            side=OrderSide.BUY,
            ratio=1,
        ),
    ]
    return ComboOrder(
        symbol=underlying,
        side=OrderSide.BUY,
        quantity=quantity,
        account_id=account_id,
        legs=legs,
    )


def build_iron_butterfly(
    account_id: str,
    underlying: Symbol,
    quantity: Decimal,
    expiry: date,
    atm_strike: Decimal,
    long_put_strike: Decimal,
    long_call_strike: Decimal,
) -> ComboOrder:
    """Builds a short Iron Butterfly order."""
    legs = [
        OptionLeg(
            symbol=_make_option_symbol(
                underlying, expiry, long_put_strike, OptionRight.PUT
            ),
            side=OrderSide.BUY,
            ratio=1,
        ),
        OptionLeg(
            symbol=_make_option_symbol(underlying, expiry, atm_strike, OptionRight.PUT),
            side=OrderSide.SELL,
            ratio=1,
        ),
        OptionLeg(
            symbol=_make_option_symbol(
                underlying, expiry, atm_strike, OptionRight.CALL
            ),
            side=OrderSide.SELL,
            ratio=1,
        ),
        OptionLeg(
            symbol=_make_option_symbol(
                underlying, expiry, long_call_strike, OptionRight.CALL
            ),
            side=OrderSide.BUY,
            ratio=1,
        ),
    ]
    return ComboOrder(
        symbol=underlying,
        side=OrderSide.BUY,
        quantity=quantity,
        account_id=account_id,
        legs=legs,
    )


def build_protective_put(
    account_id: str,
    underlying: Symbol,
    quantity: Decimal,
    expiry: date,
    put_strike: Decimal,
) -> ComboOrder:
    """Builds a protective put order (just the option leg, assuming equity is already held)."""
    legs = [
        OptionLeg(
            symbol=_make_option_symbol(underlying, expiry, put_strike, OptionRight.PUT),
            side=OrderSide.BUY,
            ratio=1,
        )
    ]
    return ComboOrder(
        symbol=underlying,
        side=OrderSide.BUY,
        quantity=quantity,
        account_id=account_id,
        legs=legs,
    )


def build_collar(
    account_id: str,
    underlying: Symbol,
    quantity: Decimal,
    expiry: date,
    put_strike: Decimal,
    call_strike: Decimal,
) -> ComboOrder:
    """Builds a collar order (protective put + covered call)."""
    legs = [
        OptionLeg(
            symbol=_make_option_symbol(underlying, expiry, put_strike, OptionRight.PUT),
            side=OrderSide.BUY,
            ratio=1,
        ),
        OptionLeg(
            symbol=_make_option_symbol(
                underlying, expiry, call_strike, OptionRight.CALL
            ),
            side=OrderSide.SELL,
            ratio=1,
        ),
    ]
    return ComboOrder(
        symbol=underlying,
        side=OrderSide.BUY,
        quantity=quantity,
        account_id=account_id,
        legs=legs,
    )
