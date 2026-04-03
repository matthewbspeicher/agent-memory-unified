from datetime import date as date_type
from decimal import Decimal

from ib_async import Stock, Option, Forex, Future, Bond, Contract

from broker.models import Symbol, AssetType, OptionRight


_SEC_TYPE_MAP = {
    AssetType.STOCK: "STK",
    AssetType.OPTION: "OPT",
    AssetType.FUTURE: "FUT",
    AssetType.FOREX: "CASH",
    AssetType.BOND: "BOND",
}

_SEC_TYPE_REVERSE = {v: k for k, v in _SEC_TYPE_MAP.items()}


def to_contract(symbol: Symbol) -> Contract:
    match symbol.asset_type:
        case AssetType.STOCK:
            return Stock(
                symbol=symbol.ticker,
                exchange=symbol.exchange or "SMART",
                currency=symbol.currency,
            )
        case AssetType.OPTION:
            right = "C" if symbol.right == OptionRight.CALL else "P"
            expiry_str = symbol.expiry.strftime("%Y%m%d") if symbol.expiry else ""
            return Option(
                symbol=symbol.ticker,
                lastTradeDateOrContractMonth=expiry_str,
                strike=float(symbol.strike) if symbol.strike else 0.0,
                right=right,
                exchange=symbol.exchange or "SMART",
                currency=symbol.currency,
            )
        case AssetType.FOREX:
            pair = symbol.ticker.split(".")
            return Forex(
                symbol=pair[0],
                currency=pair[1] if len(pair) > 1 else symbol.currency,
                exchange=symbol.exchange or "IDEALPRO",
            )
        case AssetType.FUTURE:
            expiry_str = symbol.expiry.strftime("%Y%m") if symbol.expiry else ""
            return Future(
                symbol=symbol.ticker,
                lastTradeDateOrContractMonth=expiry_str,
                exchange=symbol.exchange or "CME",
                currency=symbol.currency,
            )
        case AssetType.BOND:
            return Bond(
                symbol=symbol.ticker,
                exchange=symbol.exchange or "SMART",
                currency=symbol.currency,
            )


def from_contract(contract: Contract) -> Symbol:
    asset_type = _SEC_TYPE_REVERSE.get(contract.secType, AssetType.STOCK)

    if asset_type == AssetType.FOREX:
        ticker = f"{contract.symbol}.{contract.currency}"
    else:
        ticker = contract.symbol

    expiry = None
    if contract.lastTradeDateOrContractMonth:
        ds = contract.lastTradeDateOrContractMonth
        if len(ds) == 8:
            expiry = date_type(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
        elif len(ds) == 6:
            expiry = date_type(int(ds[:4]), int(ds[4:6]), 1)

    strike = Decimal(str(contract.strike)) if contract.strike else None
    right = None
    if contract.right == "C":
        right = OptionRight.CALL
    elif contract.right == "P":
        right = OptionRight.PUT

    multiplier = int(contract.multiplier) if contract.multiplier else None

    return Symbol(
        ticker=ticker,
        asset_type=asset_type,
        exchange=contract.exchange or None,
        currency=contract.currency,
        expiry=expiry,
        strike=strike,
        right=right,
        multiplier=multiplier,
    )
