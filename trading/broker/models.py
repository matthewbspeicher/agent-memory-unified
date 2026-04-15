from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class AssetType(str, Enum):
    STOCK = "STOCK"
    OPTION = "OPTION"
    FUTURE = "FUTURE"
    FOREX = "FOREX"
    BOND = "BOND"
    PREDICTION = "PREDICTION"  # Kalshi / Polymarket contracts
    CRYPTO = "CRYPTO"


class OptionRight(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TIF(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    GTD = "GTD"


class OrderStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Symbol:
    ticker: str
    asset_type: AssetType = AssetType.STOCK
    exchange: str | None = None
    currency: str = "USD"
    expiry: date | None = None
    strike: Decimal | None = None
    right: OptionRight | None = None
    multiplier: int | None = None


@dataclass
class OrderBase:
    symbol: Symbol
    side: OrderSide
    quantity: Decimal
    account_id: str
    time_in_force: TIF = TIF.DAY
    signal_id: str | None = None


@dataclass
class MarketOrder(OrderBase):
    pass


@dataclass
class LimitOrder(OrderBase):
    limit_price: Decimal = Decimal("0")


@dataclass
class StopOrder(OrderBase):
    stop_price: Decimal = Decimal("0")


@dataclass
class StopLimitOrder(OrderBase):
    stop_price: Decimal = Decimal("0")
    limit_price: Decimal = Decimal("0")


@dataclass
class TrailingStopOrder(OrderBase):
    trail_amount: Decimal | None = None
    trail_percent: Decimal | None = None

    def __post_init__(self):
        has_amount = self.trail_amount is not None
        has_percent = self.trail_percent is not None
        if has_amount == has_percent:
            raise ValueError("exactly one of trail_amount or trail_percent must be set")


@dataclass(frozen=True)
class OptionLeg:
    symbol: Symbol
    side: OrderSide
    ratio: int


@dataclass
class ComboOrder(OrderBase):
    legs: list[OptionLeg] = field(default_factory=list)


@dataclass
class BracketOrder(OrderBase):
    """Entry order + take-profit + stop-loss as a single atomic submission.

    take_profit_price and stop_loss_price are REQUIRED — no defaults.
    A BracketOrder with stop-loss at $0 would trigger immediately.
    """

    entry_type: str = "market"
    entry_limit_price: Decimal | None = None
    take_profit_price: Decimal = field(
        default=Decimal("-1")
    )  # sentinel — validated in __post_init__
    stop_loss_price: Decimal = field(
        default=Decimal("-1")
    )  # sentinel — validated in __post_init__
    stop_loss_limit_price: Decimal | None = None

    def __post_init__(self):
        if self.take_profit_price <= 0:
            raise ValueError("take_profit_price is required and must be positive")
        if self.stop_loss_price <= 0:
            raise ValueError("stop_loss_price is required and must be positive")


@dataclass(frozen=True)
class Quote:
    symbol: Symbol
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    volume: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class Bar:
    symbol: Symbol
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class Position:
    symbol: Symbol
    quantity: Decimal
    avg_cost: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True)
class Account:
    account_id: str
    account_type: str = ""


@dataclass(frozen=True)
class AccountBalance:
    account_id: str
    net_liquidation: Decimal
    buying_power: Decimal
    cash: Decimal
    maintenance_margin: Decimal


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    message: str | None = None
    commission: Decimal = Decimal("0")
    filled_at: datetime | None = None


@dataclass(frozen=True)
class ContractDetails:
    symbol: Symbol
    long_name: str = ""
    industry: str = ""
    category: str = ""
    min_tick: Decimal = Decimal("0.01")
    trading_hours: str = ""
    expires_at: datetime | None = None


class FeeModel(ABC):
    """Abstract base for broker commission/fee calculations."""

    @abstractmethod
    def calculate(self, order: "OrderBase", fill_price: Decimal) -> Decimal:
        """Return the total commission for this fill (always >= 0)."""


class ZeroFeeModel(FeeModel):
    """No commissions — used for prediction markets or fee-free brokers."""

    def calculate(self, order: "OrderBase", fill_price: Decimal) -> Decimal:
        return Decimal("0")


class FidelityFeeModel(FeeModel):
    """
    Fidelity Investments equity fee schedule (as of 2025).

    - Stocks/ETFs: $0 online commission.
    - Options:     $0.65 per contract.
    - Regulatory:  SEC fee on sales ($0.0000278 × notional, min $0.01).
    """

    OPTION_PER_CONTRACT = Decimal("0.65")
    # SEC fee rate: $27.80 per $1,000,000 notional = 0.0000278
    SEC_FEE_RATE = Decimal("0.0000278")

    def calculate(self, order: "OrderBase", fill_price: Decimal) -> Decimal:
        notional = fill_price * order.quantity
        commission = Decimal("0")

        if order.symbol.asset_type == AssetType.OPTION:
            commission += self.OPTION_PER_CONTRACT * order.quantity

        if order.side == OrderSide.SELL:
            sec_fee = max(Decimal("0.01"), notional * self.SEC_FEE_RATE)
            commission += sec_fee

        return commission.quantize(Decimal("0.01"))


class IBKRFeeModel(FeeModel):
    """
    IBKR Pro tiered fee schedule (US stocks, as of 2025).

    - Stocks: $0.0035 per share, min $0.35, max 1% of trade value.
    - Options: $0.65 per contract, min $1.00.
    - Regulatory: FINRA TAF on sells ($0.000166/share, max $8.30).
    """

    STOCK_PER_SHARE = Decimal("0.0035")
    STOCK_MIN = Decimal("0.35")
    OPTION_PER_CONTRACT = Decimal("0.65")
    OPTION_MIN = Decimal("1.00")
    # FINRA TAF rate
    FINRA_TAF_RATE = Decimal("0.000166")
    FINRA_TAF_MAX = Decimal("8.30")

    def calculate(self, order: "OrderBase", fill_price: Decimal) -> Decimal:
        notional = fill_price * order.quantity
        commission = Decimal("0")

        if order.symbol.asset_type == AssetType.OPTION:
            raw = self.OPTION_PER_CONTRACT * order.quantity
            commission += max(self.OPTION_MIN, raw)
        else:
            # Stocks / ETFs
            raw = self.STOCK_PER_SHARE * order.quantity
            capped = min(raw, notional * Decimal("0.01"))
            commission += max(self.STOCK_MIN, capped)

        if order.side == OrderSide.SELL:
            finra = min(self.FINRA_TAF_MAX, self.FINRA_TAF_RATE * order.quantity)
            commission += finra

        return commission.quantize(Decimal("0.0001"))


class KalshiFeeModel(FeeModel):
    """Kalshi prediction market fee schedule.

    - Taker fee: 2% of notional
    - Maker fee: 0% (rebate)
    """

    TAKER_FEE_RATE = Decimal("0.02")
    MAKER_FEE_RATE = Decimal("0.00")

    def calculate(self, order: "OrderBase", fill_price: Decimal) -> Decimal:
        notional = fill_price * order.quantity
        return (notional * self.TAKER_FEE_RATE).quantize(Decimal("0.01"))


class PolymarketFeeModel(FeeModel):
    """Polymarket prediction market fee schedule.

    - Taker fee: 2% of notional
    - Maker fee: 1% of notional
    """

    TAKER_FEE_RATE = Decimal("0.02")
    MAKER_FEE_RATE = Decimal("0.01")

    def calculate(self, order: "OrderBase", fill_price: Decimal) -> Decimal:
        notional = fill_price * order.quantity
        return (notional * self.TAKER_FEE_RATE).quantize(Decimal("0.01"))


class BinanceFeeModel(FeeModel):
    """Binance spot fee schedule.

    - Spot taker: 0.1%
    - Spot maker: 0.1%
    """

    SPOT_TAKER = Decimal("0.001")
    SPOT_MAKER = Decimal("0.001")

    def calculate(self, order: "OrderBase", fill_price: Decimal) -> Decimal:
        notional = fill_price * order.quantity
        return (notional * self.SPOT_TAKER).quantize(Decimal("0.0001"))


class BinanceFuturesFeeModel(FeeModel):
    """Binance futures fee schedule.

    - Futures taker: 0.04%
    - Futures maker: 0.02%
    """

    FUTURES_TAKER = Decimal("0.0004")
    FUTURES_MAKER = Decimal("0.0002")

    def calculate(self, order: "OrderBase", fill_price: Decimal) -> Decimal:
        notional = fill_price * order.quantity
        return (notional * self.FUTURES_TAKER).quantize(Decimal("0.0001"))


@dataclass
class OptionsChain:
    symbol: Symbol
    expirations: list[date] = field(default_factory=list)
    strikes: list[Decimal] = field(default_factory=list)
    calls: list[ContractDetails] = field(default_factory=list)
    puts: list[ContractDetails] = field(default_factory=list)


@dataclass
class OrderHistoryFilter:
    start_date: date | None = None
    end_date: date | None = None
    status: OrderStatus | None = None
    symbol: Symbol | None = None


@dataclass(frozen=True)
class BrokerCapabilities:
    stocks: bool = True
    options: bool = False
    futures: bool = False
    forex: bool = False
    bonds: bool = False
    streaming: bool = False
    prediction_markets: bool = False


@dataclass(frozen=True)
class PredictionContract:
    """Represents a Kalshi or Polymarket binary contract."""

    ticker: str  # e.g. "HIGHNY-25MAR26-B72"
    title: str  # Human-readable question
    category: str  # "economics", "politics", "climate", …
    close_time: datetime
    # Cents-based probability (0–100). None if market not yet open.
    yes_bid: int | None = None
    yes_ask: int | None = None
    yes_last: int | None = None
    open_interest: int = 0
    volume_24h: int = 0
    result: str | None = None  # "YES" | "NO" | None (unresolved)
    # Platform-specific market identifier for live orderbook lookups.
    # Kalshi: market ticker (e.g. "HIGHNY-25MAR26-B72")
    # Polymarket: condition_id (e.g. "0x1234...")
    # None when only event-level data is available.
    native_market_id: str | None = None

    @property
    def as_symbol(self) -> Symbol:
        """Map to Symbol so existing Opportunity / risk code is unchanged."""
        return Symbol(ticker=self.ticker, asset_type=AssetType.PREDICTION)

    @property
    def mid_probability(self) -> float | None:
        """Best-effort mid price as a 0–1 probability."""
        if self.yes_bid is not None and self.yes_ask is not None:
            return (self.yes_bid + self.yes_ask) / 2 / 100
        if self.yes_last is not None:
            return self.yes_last / 100
        return None
