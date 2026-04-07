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
    StopOrder,
    Symbol,
    ZeroFeeModel,
)
from storage.paper import PaperStore

logger = logging.getLogger(__name__)

PAPER_ACCOUNT_ID = "PAPER"


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
    def __init__(self, store: PaperStore) -> None:
        self._store = store

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

    async def apply_carry_fees(self, positions: list[Position], daily_rate: Decimal = Decimal("0.0001")) -> Decimal:
        """Deduct holding costs for open positions overnight."""
        total_fee = Decimal("0")
        for pos in positions:
            position_value = abs(pos.market_value)
            fee = position_value * daily_rate
            total_fee += fee
            
        # Deduct from paper cash balance in DB
        db = await self._store._get_db()
        await db.execute(
            "UPDATE paper_accounts SET cash = cash - ? WHERE account_id = ?",
            (float(total_fee), PAPER_ACCOUNT_ID)
        )
        await db.commit()
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


class PaperOrderManager(OrderManager):
    """Simulates immediate fills at current market price + random slippage."""

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

    async def place_order(self, account_id: str, order: OrderBase) -> OrderResult:
        order_id = str(uuid.uuid4())

        # --- Determine fill price ---
        quote = await self._market_data.get_quote(order.symbol)

        if isinstance(order, MarketOrder):
            if quote is not None:
                raw_price = quote.ask if order.side == OrderSide.BUY else quote.bid
                if raw_price is None:
                    raw_price = quote.last
            else:
                raw_price = None
        elif isinstance(order, LimitOrder):
            raw_price = order.limit_price
        elif isinstance(order, StopOrder):
            raw_price = order.stop_price
        else:
            # Fallback: use quote last or limit_price if available
            raw_price = getattr(order, "limit_price", None) or (
                quote.last if quote else None
            )

        if raw_price is None:
            logger.warning(
                "PaperBroker: no price available for %s", order.symbol.ticker
            )
            raise ValueError(f"No market data available for {order.symbol.ticker}")

        fill_price = self._apply_slippage(raw_price, order.side)

        # Calculate fees
        commission = self._fee_model.calculate(order, fill_price)

        # --- Persist fill + order record via PaperStore ---
        db = await self._store._get_db()
        try:
            await db.execute("BEGIN")
            await self._store.record_fill(
                account_id,
                order.symbol,
                order.side,
                order.quantity,
                fill_price,
                commission,
            )
            result = OrderResult(
                order_id=order_id,
                status=OrderStatus.FILLED,
                filled_quantity=order.quantity,
                avg_fill_price=fill_price,
                commission=commission,
            )
            await self._store.save_order(
                order_id,
                account_id,
                order.symbol,
                order.side,
                order.quantity,
                result.status.value,
                result.filled_quantity,
                result.avg_fill_price,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            "PaperBroker: PAPER %s %s x%s @ %.4f (order_id=%s, commission=%.2f)",
            order.side.value,
            order.symbol.ticker,
            order.quantity,
            fill_price,
            order_id,
            commission,
        )

        for cb in self._callbacks:
            cb(result)
        return result

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        raise NotImplementedError("PaperBroker does not support order modification")

    async def cancel_order(self, order_id: str) -> OrderResult:
        raise NotImplementedError("PaperBroker does not support order cancellation")

    async def get_order_status(self, order_id: str) -> OrderStatus:
        return OrderStatus.FILLED

    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None:
        self._callbacks.append(callback)

    async def cancel_all_orders(self) -> None:
        pass  # Simulated paper broker does not support bulk cancellation


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
        self._account_provider = PaperAccountProvider(store)
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
        db = await self._store._get_db()
        await db.executescript("""
            DELETE FROM paper_positions WHERE account_id = 'PAPER';
            DELETE FROM paper_orders   WHERE account_id = 'PAPER';
        """)
        initial = float(self._initial_balance)
        await db.execute(
            """
            INSERT OR REPLACE INTO paper_accounts
                (account_id, net_liquidation, buying_power, cash, maintenance_margin)
            VALUES (?, ?, ?, ?, 0.0)
            """,
            (PAPER_ACCOUNT_ID, initial, initial, initial),
        )
        await db.commit()
        logger.info("PaperBroker: account reset to $%.2f", self._initial_balance)
