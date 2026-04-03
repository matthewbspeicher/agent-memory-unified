from ib_async import IB

from broker.interfaces import (
    AccountProvider, Broker, BrokerConnection, MarketDataProvider, OrderManager,
)
from broker.models import BrokerCapabilities
from adapters.ibkr.connection import IBKRConnection
from adapters.ibkr.account import IBKRAccountProvider
from adapters.ibkr.market_data import IBKRMarketDataProvider
from adapters.ibkr.order_manager import IBKROrderManager


class IBKRBroker(Broker):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4001,
        client_id: int = 1,
        readonly: bool = False,
        order_timeout: int = 10,
    ):
        self._ib = IB()
        self._connection = IBKRConnection(self._ib, host, port, client_id)
        self._account = IBKRAccountProvider(self._ib)
        self._market_data = IBKRMarketDataProvider(self._ib)
        self._orders = IBKROrderManager(self._ib, order_timeout=order_timeout)

    @property
    def connection(self) -> BrokerConnection:
        return self._connection

    @property
    def account(self) -> AccountProvider:
        return self._account

    @property
    def market_data(self) -> MarketDataProvider:
        return self._market_data

    @property
    def orders(self) -> OrderManager:
        return self._orders

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            stocks=True, options=True, futures=True,
            forex=True, bonds=True, streaming=True,
        )
