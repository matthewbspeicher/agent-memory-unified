"""
PaperBroker — simulates order execution for paper trading.

Uses real market data from the MarketDataProvider but never places real orders.
Fills are simulated at the current quote with a small random slippage of 0–0.1%.
State is persisted via PaperStore.
"""

from __future__ import annotations

import logging
import random
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from broker.interfaces import (
    AccountProvider,
    Broker,
    BrokerCapabilities,
    BrokerConnection,
    MarketDataProvider,
    OrderManager,
)
from broker.models import (
    Account,
    AccountBalance,
    Bar,
    ContractDetails,
    FeeModel,
    LimitOrder,
    MarketOrder,
    OptionsChain,
    OrderBase,
    OrderHistoryFilter,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    Quote,
    is_stale,
    timestamp_age_seconds,
    StopOrder,
    StopLimitOrder,
    Symbol,
    ZeroFeeModel,
)
from broker.paper_dispatch import PaperDispatchMixin
from broker.paper_matching import PaperOrderMustRest
from storage.paper import PaperStore
from storage.unit_of_work import PaperWriteNotStarted

logger = logging.getLogger(__name__)

PAPER_ACCOUNT_ID = "PAPER"


def executable_paper_price(
    order: OrderBase, quote: Quote | None
) -> tuple[Decimal, Decimal | None]:
    """Return executable quote price and optional hard limit, never a synthetic fill.

    Raises PaperOrderMustRest for a limit that is not marketable or a stop that
    is not triggered; whether such an order rests is the caller's decision.
    Any other ValueError is a definite rejection.
    """
    if quote is None or quote.symbol != order.symbol:
        raise ValueError("No market data available for fill simulation")
    if is_stale(timestamp_age_seconds(quote.timestamp)):
        raise ValueError("Market quote is stale")
    price = quote.ask if order.side == OrderSide.BUY else quote.bid
    price = price if price is not None else quote.last
    if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        raise ValueError("Market quote is invalid")
    if type(order) not in {MarketOrder, LimitOrder, StopOrder, StopLimitOrder}:
        raise ValueError("Unsupported immediate paper order type")
    if isinstance(order, (StopOrder, StopLimitOrder)):
        triggered = (
            price >= order.stop_price
            if order.side == OrderSide.BUY
            else price <= order.stop_price
        )
        if not triggered:
            raise PaperOrderMustRest(
                "Stop is not triggered; resting orders are unsupported",
                stop_triggered=False,
            )
    limit = (
        order.limit_price if isinstance(order, (LimitOrder, StopLimitOrder)) else None
    )
    if limit is not None:
        marketable = price <= limit if order.side == OrderSide.BUY else price >= limit
        if not marketable:
            raise PaperOrderMustRest(
                "Limit is not marketable; resting orders are unsupported",
                stop_triggered=isinstance(order, StopLimitOrder),
            )
    return price, limit


def cap_paper_slippage(
    price: Decimal, limit: Decimal | None, side: OrderSide
) -> Decimal:
    if limit is None:
        return price
    return min(price, limit) if side == OrderSide.BUY else max(price, limit)


# ---------------------------------------------------------------------------
# Connection — always "connected" (no real network dependency)
# ---------------------------------------------------------------------------


class PaperBrokerConnection(BrokerConnection):
    def __init__(self) -> None:
        self._connected = False
        self._callbacks: list[Callable[[], Any]] = []

    async def connect(self) -> None:
        self._connected = True
        logger.info("PaperBroker: connected (simulated)")

    async def disconnect(self) -> None:
        self._connected = False
        for cb in self._callbacks:
            cb()

    def is_connected(self) -> bool:
        return self._connected

    def on_disconnected(self, callback: Callable[[], Any]) -> None:
        self._callbacks.append(callback)

    async def reconnect(self) -> None:
        await self.connect()


# ---------------------------------------------------------------------------
# Account — delegates to PaperStore
# ---------------------------------------------------------------------------


class PaperAccountProvider(AccountProvider):
    def __init__(self, store: PaperStore, market_data=None) -> None:
        self._store = store
        self._market_data = market_data

    async def get_risk_state(self, account_id: str):
        return await self._store.get_risk_state(account_id, self._market_data)

    async def get_accounts(self) -> list[Account]:
        return [Account(account_id=PAPER_ACCOUNT_ID, account_type="PAPER")]

    async def get_positions(self, account_id: str) -> list[Position]:
        return await self._store.get_positions(account_id)

    async def get_balances(self, account_id: str) -> AccountBalance:
        return await self._store.get_balance(account_id)

    async def get_order_history(
        self, account_id: str, filters: OrderHistoryFilter | None = None
    ) -> list[OrderResult]:
        return await self._store.get_order_history(account_id)

    async def apply_carry_fees(
        self, positions: list[Position], daily_rate: Decimal = Decimal("0.0001")
    ) -> Decimal:
        """Deduct holding costs for open positions overnight."""
        total_fee = Decimal("0")
        for pos in positions:
            position_value = (
                abs(pos.market_value)
                if pos.market_value
                else abs(pos.avg_cost * pos.quantity)
            )
            fee = position_value * daily_rate
            total_fee += fee

        # Deduct from paper cash balance in DB
        async with self._store.transaction():
            await self._store.debit_cash(PAPER_ACCOUNT_ID, total_fee)
            await self._store.record_risk_event(
                PAPER_ACCOUNT_ID, "carry_fee", -total_fee
            )
        return total_fee


# ---------------------------------------------------------------------------
# Market Data — delegates to actual provider (wired after construction)
# ---------------------------------------------------------------------------


class PaperMarketData(MarketDataProvider):
    """Thin shim that forwards market-data calls to the actual provider."""

    def __init__(self, actual_provider: MarketDataProvider | None = None) -> None:
        self._actual = actual_provider

    async def get_quote(self, symbol: Symbol) -> Quote | None:
        if self._actual is None:
            return None
        return await self._actual.get_quote(symbol)

    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]:
        if self._actual is None:
            return []
        return await self._actual.get_quotes(symbols)

    async def stream_quotes(
        self, symbols: list[Symbol], callback: Callable[[Quote], Any]
    ) -> None:
        if self._actual is not None:
            await self._actual.stream_quotes(symbols, callback)

    async def get_historical(
        self, symbol: Symbol, timeframe: str, period: str
    ) -> list[Bar]:
        if self._actual is None:
            return []
        return await self._actual.get_historical(symbol, timeframe, period)

    async def get_options_chain(
        self, symbol: Symbol, expiry: str | None = None
    ) -> OptionsChain:
        if self._actual is None:
            raise ValueError("Market data provider not initialized")
        return await self._actual.get_options_chain(symbol, expiry)

    async def get_contract_details(self, symbol: Symbol) -> ContractDetails:
        if self._actual is None:
            return ContractDetails(symbol=symbol)
        return await self._actual.get_contract_details(symbol)


# ---------------------------------------------------------------------------
# Orders — simulate fills with slippage
# ---------------------------------------------------------------------------


class ImmediatePaperOrderManager(PaperDispatchMixin, OrderManager):
    """Fill a marketable order at once and record it in the Paper ledger.

    One implementation for every paper venue. A venue supplies its slippage and,
    where it has them, its commission, the orders it refuses outright, the quote
    errors it treats as a rejection, and its fill log line. Resting, matching,
    amendment, cancellation and dispatch come from the mixins.
    """

    # Errors from the quote source that mean "reject this order", not "fail".
    rejectable_quote_errors: tuple[type[BaseException], ...] = ()

    def _refusal(self, order: OrderBase) -> str | None:
        """A reason this venue will not take the order at all, or None."""
        return None

    async def _slipped_price(self, order: OrderBase, price: Decimal) -> Decimal:
        raise NotImplementedError

    def _commission(self, order: OrderBase, fill_price: Decimal) -> Decimal:
        return Decimal("0")

    def _log_fill(self, order, fill_price, order_id, commission) -> None:
        pass

    async def _place_immediate_order(
        self, account_id: str, order: OrderBase
    ) -> OrderResult:
        refusal = self._refusal(order)
        if refusal is not None:
            return OrderResult(order_id="", status=OrderStatus.REJECTED, message=refusal)
        try:
            quote = await self._market_data.get_quote(order.symbol)
        except PaperOrderMustRest:
            raise  # a ValueError itself, so this must come first
        except self.rejectable_quote_errors as exc:
            return OrderResult(
                order_id="", status=OrderStatus.REJECTED, message=str(exc)
            )
        try:
            price, limit = executable_paper_price(order, quote)
        except PaperOrderMustRest:
            raise  # a ValueError itself, so this must come first
        except ValueError as exc:
            return OrderResult(
                order_id="", status=OrderStatus.REJECTED, message=str(exc)
            )
        fill_price = cap_paper_slippage(
            await self._slipped_price(order, price), limit, order.side
        )
        commission = self._commission(order, fill_price)
        order_id = str(uuid.uuid4())
        try:
            async with self._store.transaction():
                await self._store.record_fill(
                    account_id=account_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    fill_price=fill_price,
                    commission=commission,
                    order_id=order_id,
                )
                result = OrderResult(
                    order_id=order_id,
                    status=OrderStatus.FILLED,
                    filled_quantity=order.quantity,
                    avg_fill_price=fill_price,
                    commission=commission,
                )
                await self._store.save_order(
                    order_id=order_id,
                    account_id=account_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    status=result.status.value,
                    filled=result.filled_quantity,
                    avg_price=result.avg_fill_price,
                )
        except PaperWriteNotStarted as exc:
            return OrderResult(
                order_id="", status=OrderStatus.REJECTED, message=str(exc)
            )
        self._log_fill(order, fill_price, order_id, commission)
        for cb in self._callbacks:
            cb(result)
        return result

    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None:
        self._callbacks.append(callback)


class PaperOrderManager(ImmediatePaperOrderManager):
    """Immediate marketable fills plus persisted, explicitly tick-driven orders."""

    paper_account_id = "PAPER"

    def __init__(
        self,
        market_data: MarketDataProvider,
        store: PaperStore,
        max_slippage: Decimal = Decimal("0.001"),
        fee_model: FeeModel | None = None,
    ) -> None:
        self._market_data = market_data
        self._store = store
        self._max_slippage = max_slippage
        self._fee_model = fee_model or ZeroFeeModel()
        self._callbacks: list[Callable[[OrderResult], Any]] = []

    def _apply_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        """Return price adjusted by a random 0–MAX_SLIPPAGE_FRACTION slippage."""
        if self._max_slippage == 0:
            return price
        slippage = price * self._max_slippage * Decimal(str(random.random()))
        if side == OrderSide.BUY:
            return price + slippage
        return price - slippage

    async def _estimate_slippage(
        self, symbol: Symbol, quantity: Decimal, side: OrderSide, base_price: Decimal
    ) -> Decimal:
        """Estimate realistic slippage by walking the order book if available."""
        try:
            # Try to get real-time order book from market data provider
            order_book = await self._market_data.get_order_book(symbol, limit=20)
            side_key = "asks" if side == OrderSide.BUY else "bids"
            levels = order_book.get(side_key)

            if not levels:
                return self._apply_slippage(base_price, side)

            remaining = float(abs(quantity))
            total_cost = 0.0

            for price, volume in levels:
                take = min(remaining, volume)
                total_cost += take * price
                remaining -= take
                if remaining <= 0:
                    break

            # If quantity exceeds available depth, apply extra penalty for the remainder
            if remaining > 0:
                last_price = levels[-1][0]
                total_cost += remaining * last_price * (1.0 + float(self._max_slippage))

            fill_price = Decimal(str(total_cost / float(abs(quantity))))
            return fill_price

        except Exception as e:
            logger.debug(
                f"Slippage estimation failed for {symbol.ticker}, using random fallback: {e}"
            )
            return self._apply_slippage(base_price, side)

    async def _slipped_price(self, order: OrderBase, price: Decimal) -> Decimal:
        return await self._estimate_slippage(
            order.symbol, order.quantity, order.side, price
        )

    def _commission(self, order: OrderBase, fill_price: Decimal) -> Decimal:
        return self._fee_model.calculate(order, fill_price)

    def _log_fill(self, order, fill_price, order_id, commission) -> None:
        logger.info(
            "PaperBroker: PAPER %s %s x%s @ %.4f (order_id=%s, commission=%.2f)",
            order.side.value,
            order.symbol.ticker,
            order.quantity,
            fill_price,
            order_id,
            commission,
        )


# ---------------------------------------------------------------------------
# Paper Broker
# ---------------------------------------------------------------------------


class PaperBroker(Broker):
    """
    A fully self-contained paper trading broker.
    """

    def __init__(
        self,
        store: PaperStore,
        market_data: MarketDataProvider | None = None,
        initial_balance: float = 100000.0,
        max_slippage: float = 0.001,
        fee_model: FeeModel | None = None,
    ) -> None:
        self._store = store
        self._initial_balance = initial_balance
        self._connection = PaperBrokerConnection()
        self._market_data_provider = PaperMarketData(market_data)
        self._account_provider = PaperAccountProvider(store, self._market_data_provider)
        self._fee_model = fee_model or ZeroFeeModel()
        self._order_manager = PaperOrderManager(
            self._market_data_provider,
            store,
            max_slippage=Decimal(str(max_slippage)),
            fee_model=self._fee_model,
        )

    @property
    def connection(self) -> BrokerConnection:
        return self._connection

    @property
    def account(self) -> AccountProvider:
        return self._account_provider

    @property
    def market_data(self) -> MarketDataProvider:
        return self._market_data_provider

    @property
    def orders(self) -> OrderManager:
        return self._order_manager

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            stocks=True,
            options=False,
            futures=False,
            forex=False,
            bonds=False,
            streaming=False,
            prediction_markets=True,
        )

    async def reset(self) -> None:
        """Reset paper account to initial balance and clear all positions/orders."""
        await self._store.reset_account(PAPER_ACCOUNT_ID, self._initial_balance)
        logger.info("PaperBroker: account reset to $%.2f", self._initial_balance)
