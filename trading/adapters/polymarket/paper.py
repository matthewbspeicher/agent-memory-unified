"""
PolymarketPaperBroker — paper trading broker for binary Polymarket prediction contracts.

NOT a wrapper around SimulatedBroker. Binary contracts have a fundamentally
different lifecycle: they always resolve to $1.00 (YES) or $0.00 (NO) per
contract, never to a continuous market price.

P&L model (prices in 0-1 probability):
  Fill price = limit_price ± slippage_cents / 100  (clamped to [0.01, 0.99])
  Cost       = fill_price × quantity
  Payout YES = $1.00 × quantity
  Payout NO  = $0.00 × quantity
  P&L        = Payout − Cost − Commission

Account ID for this broker: "POLYMARKET_PAPER"
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from broker.interfaces import (
    AccountProvider,
    Broker,
    BrokerConnection,
    MarketDataProvider,
    OrderManager,
)
from broker.models import (
    Account,
    AccountBalance,
    Bar,
    BrokerCapabilities,
    ContractDetails,
    LimitOrder,
    OptionsChain,
    OrderBase,
    OrderHistoryFilter,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    Quote,
    Symbol,
)
from storage.paper import PaperStore

logger = logging.getLogger(__name__)

POLYMARKET_PAPER_ACCOUNT_ID = "POLYMARKET_PAPER"
DEFAULT_SLIPPAGE_CENTS = 1


def _apply_slippage(price: Decimal, side: OrderSide, slippage_cents: int) -> Decimal:
    delta = Decimal(str(slippage_cents)) / Decimal("100")
    if side == OrderSide.BUY:
        filled = price + delta
    else:
        filled = price - delta
    return max(Decimal("0.01"), min(Decimal("0.99"), filled))


class PolymarketPaperConnection(BrokerConnection):
    def __init__(self) -> None:
        self._callbacks: list[Callable[[], Any]] = []

    async def connect(self) -> None:
        logger.info("PolymarketPaperBroker: connected (paper mode)")

    async def disconnect(self) -> None:
        for cb in self._callbacks:
            cb()

    def is_connected(self) -> bool:
        return True

    def on_disconnected(self, callback: Callable[[], Any]) -> None:
        self._callbacks.append(callback)

    async def reconnect(self) -> None:
        pass


class PolymarketPaperAccount(AccountProvider):
    def __init__(self, store: PaperStore) -> None:
        self._store = store

    async def get_accounts(self) -> list[Account]:
        return [
            Account(
                account_id=POLYMARKET_PAPER_ACCOUNT_ID, account_type="polymarket_paper"
            )
        ]

    async def get_balances(self, account_id: str) -> AccountBalance:
        return await self._store.get_balance(account_id)

    async def get_positions(self, account_id: str) -> list[Position]:
        return await self._store.get_positions(account_id)

    async def get_order_history(
        self,
        account_id: str,
        filters: OrderHistoryFilter | None = None,
    ) -> list[OrderResult]:
        return await self._store.get_order_history(account_id)


class PolymarketPaperMarketData(MarketDataProvider):
    async def get_quote(self, symbol: Symbol) -> Quote:
        raise NotImplementedError(
            "PolymarketPaperBroker does not provide real-time quotes"
        )

    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]:
        return []

    async def stream_quotes(
        self,
        symbols: list[Symbol],
        callback: Callable[[Quote], Any],
    ) -> None:
        pass

    async def get_historical(
        self, symbol: Symbol, timeframe: str, period: str
    ) -> list[Bar]:
        return []

    async def get_options_chain(
        self, symbol: Symbol, expiry: str | None = None
    ) -> OptionsChain:
        raise NotImplementedError

    async def get_contract_details(self, symbol: Symbol) -> ContractDetails:
        return ContractDetails(symbol=symbol)


class PolymarketPaperOrderManager(OrderManager):
    def __init__(
        self, store: PaperStore, slippage_cents: int = DEFAULT_SLIPPAGE_CENTS
    ) -> None:
        self._store = store
        self._slippage_cents = slippage_cents
        self._callbacks: list[Callable[[OrderResult], Any]] = []

    async def place_order(self, account_id: str, order: OrderBase) -> OrderResult:
        if not isinstance(order, LimitOrder):
            return OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                message="PolymarketPaperBroker only accepts LimitOrder",
            )

        fill_price = _apply_slippage(
            order.limit_price, order.side, self._slippage_cents
        )
        order_id = str(uuid.uuid4())

        await self._store.record_fill(
            account_id=account_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
        )
        await self._store.save_order(
            order_id=order_id,
            account_id=account_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            status=OrderStatus.FILLED.value,
            filled=order.quantity,
            avg_price=fill_price,
        )

        result = OrderResult(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            avg_fill_price=fill_price,
        )
        for cb in self._callbacks:
            cb(result)
        return result

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        raise NotImplementedError(
            "PolymarketPaperBroker does not support order modification"
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(order_id=order_id, status=OrderStatus.CANCELLED)

    async def get_order_status(self, order_id: str) -> OrderStatus:
        return OrderStatus.FILLED

    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None:
        self._callbacks.append(callback)

    async def cancel_all_orders(self) -> None:
        pass  # Polymarket paper does not support bulk cancellation


class PolymarketPaperBroker(Broker):
    """Standalone paper broker for binary Polymarket prediction contracts."""

    def __init__(
        self,
        store: PaperStore | None = None,
        slippage_cents: int = DEFAULT_SLIPPAGE_CENTS,
    ) -> None:
        self._store = store or PaperStore()
        self._connection = PolymarketPaperConnection()
        self._account = PolymarketPaperAccount(self._store)
        self._market_data = PolymarketPaperMarketData()
        self._orders = PolymarketPaperOrderManager(self._store, slippage_cents)

    @property
    def connection(self) -> PolymarketPaperConnection:
        return self._connection

    @property
    def account(self) -> PolymarketPaperAccount:
        return self._account

    @property
    def market_data(self) -> PolymarketPaperMarketData:
        return self._market_data

    @property
    def orders(self) -> PolymarketPaperOrderManager:
        return self._orders

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(prediction_markets=True)

    async def resolve_contract(
        self,
        account_id: str,
        symbol: Symbol,
        quantity: Decimal,
        entry_price: Decimal,
        resolution: str,
    ) -> None:
        """Settle a binary contract. Call this when Polymarket publishes a result."""
        await self._store.record_binary_resolution(
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            resolution=resolution,
        )
        logger.info(
            "PolymarketPaperBroker: resolved %s %s x%s @ entry %s → %s",
            account_id,
            symbol.ticker,
            quantity,
            entry_price,
            resolution,
        )
