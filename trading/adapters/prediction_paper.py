"""Paper trading for binary prediction contracts, shared by every venue.

Binary contracts always resolve to $1.00 (YES) or $0.00 (NO) per contract, never
to a continuous market price.

P&L model (prices are probabilities, 0.01 to 0.99):
  Fill price = quote price ± slippage_cents / 100, clamped and capped by the limit
  Cost       = fill_price × quantity
  Payout YES = $1.00 × quantity
  Payout NO  = $0.00 × quantity
  P&L        = Payout − Cost − Commission

A venue is a set of subclasses that name it and its paper account.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from broker.interfaces import (
    AccountProvider,
    Broker,
    BrokerConnection,
    MarketDataProvider,
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
    Position,
    Quote,
    Symbol,
)
from broker.paper import ImmediatePaperOrderManager
from storage.paper import PaperStore

DEFAULT_SLIPPAGE_CENTS = 1  # 1¢ slippage on fills


def apply_cent_slippage(price: Decimal, side: OrderSide, slippage_cents: int) -> Decimal:
    delta = Decimal(str(slippage_cents)) / Decimal("100")
    if side == OrderSide.BUY:
        filled = price + delta  # pay a little more
    else:
        filled = price - delta  # receive a little less
    return max(Decimal("0.01"), min(Decimal("0.99"), filled))


class _Venue:
    """Mixed into each class so messages and logs name the venue."""

    venue = ""  # e.g. "Kalshi"

    @property
    def _label(self) -> str:
        return f"{self.venue}PaperBroker"

    @property
    def _log(self) -> logging.Logger:
        return logging.getLogger(type(self).__module__)


class PredictionPaperConnection(_Venue, BrokerConnection):
    """Always connected: no network is needed."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[], Any]] = []

    async def connect(self) -> None:
        self._log.info("%s: connected (paper mode)", self._label)

    async def disconnect(self) -> None:
        for cb in self._callbacks:
            cb()

    def is_connected(self) -> bool:
        return True

    def on_disconnected(self, callback: Callable[[], Any]) -> None:
        self._callbacks.append(callback)

    async def reconnect(self) -> None:
        pass


class PredictionPaperAccount(AccountProvider):
    paper_account_id = ""
    account_type = ""

    def __init__(self, store: PaperStore, market_data=None) -> None:
        self._store = store
        self._market_data = market_data

    async def get_risk_state(self, account_id: str):
        return await self._store.get_risk_state(account_id, self._market_data)

    async def get_accounts(self) -> list[Account]:
        return [
            Account(account_id=self.paper_account_id, account_type=self.account_type)
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


class PredictionPaperMarketData(_Venue, MarketDataProvider):
    """Stub used when no quote source is supplied: it has no quotes."""

    async def get_quote(self, symbol: Symbol) -> Quote:
        raise NotImplementedError(f"{self._label} does not provide real-time quotes")

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


class PredictionPaperOrderManager(_Venue, ImmediatePaperOrderManager):
    rejectable_quote_errors = (ValueError, NotImplementedError)

    def __init__(
        self,
        store: PaperStore,
        slippage_cents: int = DEFAULT_SLIPPAGE_CENTS,
        market_data: MarketDataProvider | None = None,
    ) -> None:
        self._store = store
        self._market_data = market_data
        self._slippage_cents = slippage_cents
        self._callbacks: list[Callable[[OrderResult], Any]] = []

    def _refusal(self, order: OrderBase) -> str | None:
        if not isinstance(order, LimitOrder):
            return f"{self._label} only accepts LimitOrder"
        if self._market_data is None:
            return "No market data available for fill simulation"
        return None

    async def _slipped_price(self, order: OrderBase, price: Decimal) -> Decimal:
        return apply_cent_slippage(price, order.side, self._slippage_cents)


class PredictionPaperBroker(_Venue, Broker):
    """Standalone paper broker for one venue's binary prediction contracts."""

    connection_class: type[PredictionPaperConnection] = PredictionPaperConnection
    account_class: type[PredictionPaperAccount] = PredictionPaperAccount
    market_data_class: type[PredictionPaperMarketData] = PredictionPaperMarketData
    order_manager_class: type[PredictionPaperOrderManager] = PredictionPaperOrderManager

    def __init__(
        self,
        store: PaperStore | None = None,
        slippage_cents: int = DEFAULT_SLIPPAGE_CENTS,
        market_data: MarketDataProvider | None = None,
    ) -> None:
        self._store = store or PaperStore()
        self._connection = self.connection_class()
        self._market_data = market_data or self.market_data_class()
        self._account = self.account_class(self._store, self._market_data)
        self._orders = self.order_manager_class(
            self._store, slippage_cents, self._market_data
        )

    @property
    def connection(self) -> PredictionPaperConnection:
        return self._connection

    @property
    def account(self) -> PredictionPaperAccount:
        return self._account

    @property
    def market_data(self) -> MarketDataProvider:
        return self._market_data

    @property
    def orders(self) -> PredictionPaperOrderManager:
        return self._orders

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(prediction_markets=True)

    async def resolve_contract(
        self,
        account_id: str,
        symbol: Symbol,
        quantity: Decimal,
        entry_price: Decimal,
        resolution: str,  # "YES" | "NO" | "CANCELLED"
    ) -> None:
        """Settle a binary contract. Call this when the venue publishes a result."""
        await self._store.record_binary_resolution(
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            resolution=resolution,
        )
        self._log.info(
            "%s: resolved %s %s x%s @ entry %s → %s",
            self._label,
            account_id,
            symbol.ticker,
            quantity,
            entry_price,
            resolution,
        )
