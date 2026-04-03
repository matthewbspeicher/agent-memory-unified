from broker.interfaces import (
    AccountProvider, Broker, BrokerConnection, MarketDataProvider, OrderManager,
)
from broker.models import BrokerCapabilities
from adapters.tradier.client import TradierClient
from adapters.tradier.connection import TradierConnection
from adapters.tradier.account import TradierAccountProvider
from adapters.tradier.market_data import TradierMarketDataProvider
from adapters.tradier.order_manager import TradierOrderManager


class TradierBroker(Broker):
    def __init__(
        self,
        token: str,
        account_id: str,
        sandbox: bool = True,
        order_timeout: float = 10.0,
    ) -> None:
        self._client = TradierClient(
            token=token,
            account_id=account_id,
            sandbox=sandbox,
        )
        self._connection = TradierConnection(self._client)
        self._account = TradierAccountProvider(self._client)
        self._market_data = TradierMarketDataProvider(self._client)
        self._orders = TradierOrderManager(self._client, order_timeout=order_timeout)

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
            stocks=True,
            options=True,
            futures=False,
            forex=False,
            bonds=False,
            streaming=False,  # SSE streaming deferred to Phase 2
        )
