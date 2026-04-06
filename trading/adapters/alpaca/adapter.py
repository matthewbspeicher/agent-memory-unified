from broker.interfaces import (
    AccountProvider,
    Broker,
    BrokerConnection,
    MarketDataProvider,
    OrderManager,
)
from broker.models import BrokerCapabilities
from adapters.alpaca.client import AlpacaClient
from adapters.alpaca.connection import AlpacaConnection
from adapters.alpaca.account import AlpacaAccountProvider
from adapters.alpaca.market_data import AlpacaMarketDataProvider
from adapters.alpaca.order_manager import AlpacaOrderManager


class AlpacaBroker(Broker):
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        data_feed: str = "iex",
        order_timeout: float = 10.0,
    ) -> None:
        self._client = AlpacaClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
            data_feed=data_feed,
        )
        self._connection = AlpacaConnection(self._client)
        self._market_data = AlpacaMarketDataProvider(self._client)
        self._orders = AlpacaOrderManager(self._client, order_timeout=order_timeout)
        self._account_provider: AlpacaAccountProvider | None = None

    @property
    def connection(self) -> BrokerConnection:
        return self._connection

    @property
    def account(self) -> AccountProvider:
        if self._account_provider is None:
            account_id = self._connection.account_id or ""
            self._account_provider = AlpacaAccountProvider(self._client, account_id)
        return self._account_provider

    @property
    def market_data(self) -> MarketDataProvider:
        return self._market_data

    @property
    def orders(self) -> OrderManager:
        return self._orders

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            stocks=True,
            options=False,  # Alpaca supports options but scoped to equities for Phase 1
            futures=False,
            forex=False,
            bonds=False,
            streaming=False,  # WebSocket streaming deferred to Phase 2
        )
