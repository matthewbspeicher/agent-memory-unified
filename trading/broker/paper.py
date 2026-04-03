import uuid
from collections.abc import Callable
from typing import Any
from decimal import Decimal

from broker.interfaces import Broker, BrokerConnection, AccountProvider, MarketDataProvider, OrderManager
from broker.models import (
    Account, AccountBalance, BrokerCapabilities, FeeModel, OrderBase, OrderResult, OrderStatus,
    OrderHistoryFilter, Position, MarketOrder, LimitOrder, StopOrder, ComboOrder, ZeroFeeModel,
)
from storage.paper import PaperStore


class PaperBrokerConnection(BrokerConnection):
    def __init__(self, real_connection: BrokerConnection):
        self._real = real_connection

    async def connect(self) -> None:
        await self._real.connect()

    async def disconnect(self) -> None:
        await self._real.disconnect()

    def is_connected(self) -> bool:
        return self._real.is_connected()

    def on_disconnected(self, callback: Callable[[], Any]) -> None:
        self._real.on_disconnected(callback)

    async def reconnect(self) -> None:
        await self._real.reconnect()


class PaperAccountProvider(AccountProvider):
    def __init__(self, store: PaperStore):
        self.store = store

    async def get_accounts(self) -> list[Account]:
        return [Account(account_id="PAPER", account_type="PAPER")]

    async def get_positions(self, account_id: str) -> list[Position]:
        return await self.store.get_positions(account_id)

    async def get_balances(self, account_id: str) -> AccountBalance:
        return await self.store.get_balance(account_id)

    async def get_order_history(self, account_id: str, filters: OrderHistoryFilter | None = None) -> list[OrderResult]:
        return await self.store.get_order_history(account_id)


class PaperOrderManager(OrderManager):
    def __init__(
        self,
        market_data: MarketDataProvider,
        store: PaperStore,
        fee_model: FeeModel | None = None,
    ):
        self.market_data = market_data
        self.store = store
        self._fee_model: FeeModel = fee_model or ZeroFeeModel()
        self._on_update = None

    async def place_order(self, account_id: str, order: OrderBase) -> OrderResult:
        order_id = str(uuid.uuid4())

        # Get quotes before transaction (network I/O)
        if isinstance(order, ComboOrder):
            leg_quotes = []
            for leg in order.legs:
                leg_quotes.append(await self.market_data.get_quote(leg.symbol))
        else:
            quote = await self.market_data.get_quote(order.symbol)

        # Execute fills + order record in a single transaction
        db = await self.store._get_db()
        try:
            await db.execute("BEGIN")

            commission = Decimal("0")
            if isinstance(order, ComboOrder):
                combo_fill_price = Decimal("0")
                for leg, leg_quote in zip(order.legs, leg_quotes):
                    if leg.side.value == "BUY":
                        leg_price = leg_quote.ask if leg_quote.ask else leg_quote.last
                        if not leg_price:
                            raise ValueError(f"No market data available for {leg.symbol.ticker}")
                        combo_fill_price += leg_price * leg.ratio
                    else:
                        leg_price = leg_quote.bid if leg_quote.bid else leg_quote.last
                        if not leg_price:
                            raise ValueError(f"No market data available for {leg.symbol.ticker}")
                        combo_fill_price -= leg_price * leg.ratio
                    await self.store.record_fill(account_id, leg.symbol, leg.side, order.quantity * leg.ratio, leg_price)
                fill_price = combo_fill_price
            else:
                fill_price = None
                if isinstance(order, MarketOrder):
                    fill_price = quote.ask if order.side.value == "BUY" else quote.bid
                    if not fill_price:
                        fill_price = quote.last
                elif isinstance(order, LimitOrder):
                    fill_price = order.limit_price
                elif isinstance(order, StopOrder):
                    fill_price = order.stop_price

                if not fill_price:
                    raise ValueError(f"No market data available for {order.symbol.ticker}")

                commission = self._fee_model.calculate(order, fill_price)
                await self.store.record_fill(account_id, order.symbol, order.side, order.quantity, fill_price, commission=commission)

            result = OrderResult(
                order_id=order_id,
                status=OrderStatus.FILLED,
                filled_quantity=order.quantity,
                avg_fill_price=fill_price,
                commission=commission,
            )
            await self.store.save_order(order_id, account_id, order.symbol, order.side, order.quantity, result.status.value, result.filled_quantity, result.avg_fill_price)

            await db.commit()
        except Exception:
            await db.rollback()
            raise

        if self._on_update:
            self._on_update(result)

        return result

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        raise NotImplementedError("PaperBroker doesn't support modify_order yet")

    async def cancel_order(self, order_id: str) -> OrderResult:
        raise NotImplementedError("PaperBroker doesn't support cancel_order yet")

    async def get_order_status(self, order_id: str) -> OrderStatus:
        return OrderStatus.FILLED

    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None:
        self._on_update = callback

    async def cancel_all_orders(self) -> None:
        pass  # Paper broker does not support bulk cancellation


class PaperBroker(Broker):
    def __init__(self, real_broker: Broker, store: PaperStore, fee_model: FeeModel | None = None):
        self._real_broker = real_broker
        self._store = store

        self._connection = PaperBrokerConnection(real_broker.connection)
        self._account = PaperAccountProvider(self._store)
        self._market_data = real_broker.market_data
        self._orders = PaperOrderManager(self._market_data, self._store, fee_model=fee_model)

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
        c = self._real_broker.capabilities()
        return BrokerCapabilities(
            stocks=c.stocks,
            options=c.options,
            futures=c.futures,
            forex=c.forex,
            bonds=c.bonds,
            streaming=c.streaming
        )
