from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from broker.models import (
    Account,
    AccountBalance,
    Bar,
    BrokerCapabilities,
    ContractDetails,
    OptionsChain,
    OrderBase,
    OrderHistoryFilter,
    OrderResult,
    OrderStatus,
    Position,
    Quote,
    Symbol,
)


class BrokerConnection(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def on_disconnected(self, callback: Callable[[], Any]) -> None: ...

    @abstractmethod
    async def reconnect(self) -> None: ...


class AccountProvider(ABC):
    @abstractmethod
    async def get_accounts(self) -> list[Account]: ...

    @abstractmethod
    async def get_positions(self, account_id: str) -> list[Position]: ...

    @abstractmethod
    async def get_balances(self, account_id: str) -> AccountBalance: ...

    @abstractmethod
    async def get_order_history(
        self,
        account_id: str,
        filters: OrderHistoryFilter | None = None,
    ) -> list[OrderResult]: ...


class MarketDataProvider(ABC):
    @abstractmethod
    async def get_quote(self, symbol: Symbol) -> Quote: ...

    @abstractmethod
    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]: ...

    async def get_order_book(self, symbol: Symbol, limit: int = 20) -> dict:
        """Get order book. Optional for all providers — default returns empty; override for exchange-backed providers."""
        return {"bids": [], "asks": []}

    @abstractmethod
    async def stream_quotes(
        self,
        symbols: list[Symbol],
        callback: Callable[[Quote], Any],
    ) -> None: ...

    @abstractmethod
    async def get_historical(
        self,
        symbol: Symbol,
        timeframe: str,
        period: str,
    ) -> list[Bar]: ...

    @abstractmethod
    async def get_options_chain(
        self,
        symbol: Symbol,
        expiry: str | None = None,
    ) -> OptionsChain: ...

    @abstractmethod
    async def get_contract_details(self, symbol: Symbol) -> ContractDetails: ...


class OrderManager(ABC):
    @abstractmethod
    async def place_order(self, account_id: str, order: OrderBase) -> OrderResult: ...

    @abstractmethod
    async def modify_order(
        self, order_id: str, changes: dict[str, object]
    ) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> OrderResult: ...

    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderStatus: ...

    @abstractmethod
    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None: ...

    @abstractmethod
    async def cancel_all_orders(self) -> None: ...


class Broker(ABC):
    @property
    @abstractmethod
    def connection(self) -> BrokerConnection: ...

    @property
    @abstractmethod
    def account(self) -> AccountProvider: ...

    @property
    @abstractmethod
    def market_data(self) -> MarketDataProvider: ...

    @property
    @abstractmethod
    def orders(self) -> OrderManager: ...

    @abstractmethod
    def capabilities(self) -> BrokerCapabilities: ...


class MultiAccountBroker:
    """Unified interface for managing multiple broker accounts."""

    def __init__(self):
        self._accounts: dict[str, Broker] = {}

    def register_account(self, account_id: str, broker: Broker):
        """Map an account ID to a specific broker instance."""
        self._accounts[account_id] = broker

    def get_broker(self, account_id: str) -> Broker | None:
        """Retrieve the broker instance for a given account ID."""
        return self._accounts.get(account_id)

    def list_accounts(self) -> list[str]:
        """Return all registered account IDs."""
        return list(self._accounts.keys())
