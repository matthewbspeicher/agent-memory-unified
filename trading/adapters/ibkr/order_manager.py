import asyncio
from collections.abc import Callable
from typing import Any

from ib_async import IB

from broker.interfaces import OrderManager
from broker.models import MarketOrder, OrderBase, OrderResult, OrderStatus
from adapters.ibkr.symbols import to_contract
from adapters.ibkr.orders import to_ib_order, to_order_result

FILL_TERMINAL = {"Filled", "Cancelled", "ApiCancelled", "Inactive"}
SUBMIT_TERMINAL = {"Submitted", "PreSubmitted", "Cancelled", "ApiCancelled", "Inactive"}


class IBKROrderManager(OrderManager):
    def __init__(self, ib: IB, order_timeout: int = 10):
        self._ib = ib
        self._order_timeout = order_timeout
        self._order_callbacks: list[Callable[[OrderResult], Any]] = []

    async def place_order(self, account_id: str, order: OrderBase) -> OrderResult:
        contract = to_contract(order.symbol)
        await self._ib.qualifyContractsAsync(contract)
        ib_order = to_ib_order(order)
        trade = self._ib.placeOrder(contract, ib_order)

        terminal_states = (
            FILL_TERMINAL if isinstance(order, MarketOrder) else SUBMIT_TERMINAL
        )
        event = asyncio.Event()

        def on_status(t):
            if t.orderStatus.status in terminal_states:
                event.set()

        trade.statusEvent += on_status
        try:
            await asyncio.wait_for(event.wait(), timeout=self._order_timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            trade.statusEvent -= on_status

        return to_order_result(trade)

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        trades = self._ib.trades()
        trade = next((t for t in trades if str(t.order.orderId) == order_id), None)
        if not trade:
            from broker.errors import BrokerError

            raise BrokerError(f"Order {order_id} not found")

        for key, value in changes.items():
            if hasattr(trade.order, key):
                setattr(trade.order, key, value)

        ack_states = {"Submitted", "PreSubmitted"}
        event = asyncio.Event()

        def on_status(t):
            if t.orderStatus.status in ack_states:
                event.set()

        def on_error(req_id, error_code, error_string, contract):
            if error_code == 201:
                event.set()

        trade.statusEvent += on_status
        self._ib.errorEvent += on_error
        try:
            self._ib.placeOrder(trade.contract, trade.order)
            await asyncio.wait_for(event.wait(), timeout=self._order_timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            trade.statusEvent -= on_status
            self._ib.errorEvent -= on_error

        return to_order_result(trade)

    async def cancel_order(self, order_id: str) -> OrderResult:
        trades = self._ib.trades()
        trade = next((t for t in trades if str(t.order.orderId) == order_id), None)
        if not trade:
            from broker.errors import BrokerError

            raise BrokerError(f"Order {order_id} not found")

        event = asyncio.Event()

        def on_cancelled(t):
            event.set()

        def on_failed(t):
            event.set()

        trade.cancelledEvent += on_cancelled
        trade.cancelFailedEvent += on_failed
        try:
            self._ib.cancelOrder(trade.order)
            await asyncio.wait_for(event.wait(), timeout=self._order_timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            trade.cancelledEvent -= on_cancelled
            trade.cancelFailedEvent -= on_failed

        return to_order_result(trade)

    async def get_order_status(self, order_id: str) -> OrderStatus:
        trades = self._ib.trades()
        trade = next((t for t in trades if str(t.order.orderId) == order_id), None)
        if not trade:
            from broker.errors import BrokerError

            raise BrokerError(f"Order {order_id} not found")
        return to_order_result(trade).status

    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None:
        self._order_callbacks.append(callback)
        self._ib.orderStatusEvent += lambda trade: callback(to_order_result(trade))

    async def cancel_all_orders(self) -> None:
        self._ib.reqGlobalCancel()
