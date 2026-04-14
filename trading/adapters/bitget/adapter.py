from __future__ import annotations

import logging
from decimal import Decimal
from datetime import datetime
from collections.abc import Callable
from typing import Any

from adapters.bitget.client import BitGetClient
from broker.interfaces import (
    AccountProvider,
    Broker,
    BrokerConnection,
    MarketDataProvider,
    OrderManager,
)
from broker.models import (
    AccountBalance,
    Account,
    AssetType,
    Bar,
    BrokerCapabilities,
    ContractDetails,
    LimitOrder,
    MarketOrder,
    OptionsChain,
    OrderHistoryFilter,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    Quote,
    Symbol,
)

logger = logging.getLogger(__name__)

ACCOUNT_ID = "BITGET"


class BitGetConnection(BrokerConnection):
    def __init__(self, client: BitGetClient):
        self.client = client
        self._connected = False
        self._disconnect_callbacks: list = []

    async def connect(self) -> None:
        if self._connected:
            return
        try:
            await self.client.get_account_balance()
            self._connected = True
            logger.info("BitGet: Broker connected")
        except Exception as e:
            logger.error("BitGet: Connection failed: %s", e)
            raise

    async def disconnect(self) -> None:
        self._connected = False
        await self.client.close()
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception:
                pass

    def on_disconnected(self, callback: Callable[[], Any]) -> None:
        self._disconnect_callbacks.append(callback)

    def is_connected(self) -> bool:
        return self._connected

    async def reconnect(self) -> None:
        self._connected = False
        await self.connect()


class BitGetAccount(AccountProvider):
    def __init__(self, client: BitGetClient):
        self.client = client

    async def get_accounts(self) -> list[Account]:
        return [Account(account_id=ACCOUNT_ID)]

    async def get_balances(self, account_id: str) -> AccountBalance:
        balances = await self.client.get_balances()
        total_usd = Decimal("0")
        cash = Decimal("0")

        for bal in balances:
            avail = Decimal(bal.get("available", "0"))
            if avail > 0:
                coin = bal.get("coin", "")
                if coin == "USDT":
                    cash = avail
                total_usd += avail

        return AccountBalance(
            account_id=ACCOUNT_ID,
            net_liquidation=cash,
            cash=cash,
            buying_power=cash,
            maintenance_margin=Decimal("0"),
        )

    async def get_positions(self, account_id: str) -> list[Position]:
        positions: list[Position] = []
        try:
            assets = await self.client.get_positions()
            for asset in assets:
                qty = Decimal(asset.get("available", "0"))
                if qty <= 0:
                    continue
                positions.append(
                    Position(
                        symbol=Symbol(
                            ticker=asset.get("coin", "USDT"),
                            asset_type=AssetType.STOCK,
                        ),
                        quantity=qty,
                        avg_cost=Decimal("0"),
                        market_value=Decimal("0"),
                        unrealized_pnl=Decimal("0"),
                        realized_pnl=Decimal("0"),
                    )
                )
        except Exception as e:
            logger.error("BitGet: Failed to get positions: %s", e)
        return positions

    async def get_order_history(
        self, account_id: str, filters: OrderHistoryFilter | None = None
    ) -> list[OrderResult]:
        symbol = filters.symbol.ticker if filters and filters.symbol else None
        limit = 50

        results = []
        try:
            if symbol:
                orders = await self.client.get_order_history(symbol, limit)
            else:
                orders = await self.client.get_open_orders()

            for order in orders:
                status_map = {
                    "new": OrderStatus.SUBMITTED,
                    "partially_filled": OrderStatus.PARTIAL,
                    "filled": OrderStatus.FILLED,
                    "canceled": OrderStatus.CANCELLED,
                    "expired": OrderStatus.CANCELLED,
                }
                status_str = order.get("status", "new").lower()
                results.append(
                    OrderResult(
                        order_id=order.get("orderId", ""),
                        status=status_map.get(status_str, OrderStatus.REJECTED),
                        filled_quantity=Decimal(order.get("fillQty", "0")),
                        avg_fill_price=Decimal(order.get("fillPrice", "0")),
                    )
                )
        except Exception as e:
            logger.error("BitGet: Failed to get order history: %s", e)

        return results


class BitGetMarketData(MarketDataProvider):
    def __init__(self, client: BitGetClient):
        self.client = client

    async def get_quote(self, symbol: Symbol) -> Quote:
        try:
            ticker = await self.client.get_ticker(symbol.ticker)
            data = ticker or {}
            last = Decimal(data.get("last", "0"))
            return Quote(
                symbol=symbol,
                bid=last * Decimal("0.999"),
                ask=last * Decimal("1.001"),
                last=last,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error("BitGet: Failed to get quote for %s: %s", symbol.ticker, e)
            return Quote(
                symbol=symbol,
                bid=None,
                ask=None,
                last=None,
                timestamp=datetime.now(),
            )

    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]:
        result: list[Quote] = []
        for sym in symbols:
            q = await self.get_quote(sym)
            if q:
                result.append(q)
        return result

    async def stream_quotes(
        self, symbols: list[Symbol], callback: Callable[[Quote], Any]
    ) -> None:
        import asyncio

        symbol_map = {sym.ticker: sym for sym in symbols}

        while True:
            try:
                all_tickers = await self.client.get_all_tickers()
                for ticker in all_tickers:
                    sym_str = ticker.get("symbol")
                    if sym_str in symbol_map:
                        sym = symbol_map[sym_str]
                        last = Decimal(str(ticker.get("last", "0")))
                        q = Quote(
                            symbol=sym,
                            bid=last * Decimal("0.999"),
                            ask=last * Decimal("1.001"),
                            last=last,
                            timestamp=datetime.now(),
                        )
                        if callback:
                            callback(q)
            except Exception as e:
                logger.error("BitGet: Error streaming quotes: %s", e)
            await asyncio.sleep(5)

    async def get_historical(
        self, symbol: Symbol, timeframe: str, period: str
    ) -> list[Bar]:
        timeframe_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
            "1w": "1w",
        }
        tf = timeframe_map.get(timeframe, "1h")

        limit_map = {"1d": 90, "1w": 52, "1h": 500, "15m": 500}
        limit = limit_map.get(tf, 100)

        try:
            klines = await self.client.get_klines(symbol.ticker, tf, limit)
            bars = []
            for k in klines:
                bars.append(
                    Bar(
                        symbol=symbol,
                        timestamp=datetime.fromtimestamp(int(k[0]) / 1000),
                        open=Decimal(str(k[1])),
                        high=Decimal(str(k[2])),
                        low=Decimal(str(k[3])),
                        close=Decimal(str(k[4])),
                        volume=int(Decimal(str(k[5]))),
                    )
                )
            return bars
        except Exception as e:
            logger.error(
                "BitGet: Failed to get historical for %s: %s", symbol.ticker, e
            )
            return []

    async def get_options_chain(
        self, symbol: Symbol, expiry: str | None = None
    ) -> OptionsChain:
        return OptionsChain(symbol=symbol)

    async def get_contract_details(self, symbol: Symbol) -> ContractDetails:
        return ContractDetails(symbol=symbol)


class BitGetOrderManager(OrderManager):
    def __init__(self, client: BitGetClient, dry_run: bool = False):
        self.client = client
        self.dry_run = dry_run
        self._order_update_callback: Callable[[OrderResult], Any] | None = None
        self._order_symbols: dict[str, str] = {}

    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None:
        self._order_update_callback = callback

    async def place_order(self, account_id: str, order) -> OrderResult:
        symbol = order.symbol.ticker
        side = "buy" if order.side == OrderSide.BUY else "sell"

        if isinstance(order, MarketOrder):
            order_type = "market"
        elif isinstance(order, LimitOrder):
            order_type = "limit"
        else:
            return OrderResult(
                order_id="failed",
                status=OrderStatus.REJECTED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
                message=f"Unsupported order type: {type(order)}",
            )

        quantity = str(order.quantity)

        if self.dry_run:
            import uuid

            logger.info(
                "BitGet [DRY-RUN]: Would place %s %s %s", side, order_type, symbol
            )
            return OrderResult(
                order_id=f"dry-run-{uuid.uuid4()}",
                status=OrderStatus.SUBMITTED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
            )

        try:
            price = str(order.limit_price) if isinstance(order, LimitOrder) else None
            result = await self.client.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
            )
            order_id = result.get("orderId", "unknown")
            self._order_symbols[order_id] = symbol
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.SUBMITTED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
            )
        except Exception as e:
            logger.error("BitGet: Order failed: %s", e)
            return OrderResult(
                order_id="failed",
                status=OrderStatus.REJECTED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
                message=str(e),
            )

    async def modify_order(
        self, order_id: str, changes: dict[str, object]
    ) -> OrderResult:
        return OrderResult(
            order_id=order_id,
            status=OrderStatus.REJECTED,
            filled_quantity=Decimal("0"),
            avg_fill_price=Decimal("0"),
            message="BitGet: Order modification not supported",
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        if self.dry_run:
            logger.info("BitGet [DRY-RUN]: Would cancel order %s", order_id)
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
            )
        try:
            symbol = self._order_symbols.get(order_id, "BTCUSDT")
            await self.client.cancel_order(symbol, order_id)
            self._order_symbols.pop(order_id, None)
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
            )
        except Exception as e:
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
                message=str(e),
            )

    async def get_order_status(self, order_id: str) -> OrderStatus:
        return OrderStatus.SUBMITTED

    async def cancel_all_orders(self) -> None:
        pass


class BitGetBroker(Broker):
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        dry_run: bool = False,
    ):
        self._client = BitGetClient(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
        )
        self._conn = BitGetConnection(self._client)
        self._acct = BitGetAccount(self._client)
        self._data = BitGetMarketData(self._client)
        self._om = BitGetOrderManager(self._client, dry_run)

    @property
    def connection(self) -> BrokerConnection:
        return self._conn

    @property
    def account(self) -> AccountProvider:
        return self._acct

    @property
    def market_data(self) -> MarketDataProvider:
        return self._data

    @property
    def orders(self) -> OrderManager:
        return self._om

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            stocks=True,
            options=False,
            futures=False,
            forex=False,
            bonds=False,
            streaming=False,
            prediction_markets=False,
        )
