"""
Polymarket Broker Adapter.

Implements the standard Broker interfaces (Connection, Account, MarketData, OrderManager)
by delegating to PolymarketClient and PolymarketDataSource.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from collections.abc import Callable

from adapters.polymarket.client import PolymarketClient
from adapters.polymarket.data_source import PolymarketDataSource
from broker.interfaces import (
    Account,
    AccountBalance,
    AccountProvider,
    Broker,
    BrokerCapabilities,
    BrokerConnection,
    Bar,
    MarketDataProvider,
    OrderManager,
    Position,
)
from broker.models import (
    AssetType,
    ContractDetails,
    LimitOrder,
    MarketOrder,
    OptionsChain,
    OrderBase,
    OrderHistoryFilter,
    OrderResult,
    OrderStatus,
    OrderSide,
    Quote,
    Symbol,
)
from py_clob_client.order_builder.constants import BUY, SELL

logger = logging.getLogger(__name__)


class PolymarketConnection(BrokerConnection):
    def __init__(self, client: PolymarketClient, creds_path: str, dry_run: bool):
        self.client = client
        self.creds_path = creds_path
        self.dry_run = dry_run
        self._connected = False
        self._disconnect_callbacks: list = []

    async def connect(self) -> None:
        if self._connected:
            return

        logger.info("Polymarket: Authenticating L2 credentials...")
        try:
            self.client.authenticate(self.creds_path)

            logger.info(
                "Polymarket: Setting up on-chain approvals (dry-run=%s)...",
                self.dry_run,
            )
            self.client.setup_approvals(self.dry_run)

            if not self.client.check_health():
                raise ConnectionError(
                    "Polymarket CLOB health check failed after authenticate()"
                )
        except Exception as e:
            msg = str(e)
            if (
                "401" in msg
                or "404" in msg
                or "Invalid L1 Request headers" in msg
                or "status_code" in msg
            ):
                logger.warning(
                    "Polymarket auth failed (continuing in read-only mode): %s", e
                )
            else:
                raise

        self._connected = True
        logger.info("Polymarket: Broker connected and ready.")

    async def disconnect(self) -> None:
        self._connected = False
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception:
                pass

    def on_disconnected(self, callback) -> None:
        self._disconnect_callbacks.append(callback)

    def is_connected(self) -> bool:
        return self._connected and self.client.clob.creds is not None

    async def reconnect(self) -> None:
        self._connected = False
        await self.connect()


class PolymarketAccount(AccountProvider):
    ACCOUNT_ID = "POLYMARKET"

    def __init__(self, client: PolymarketClient):
        self.client = client

    async def get_accounts(self) -> list[Account]:
        return [Account(account_id=self.ACCOUNT_ID, account_type="POLYMARKET")]

    async def get_balances(self, account_id: str = "") -> AccountBalance:
        try:
            # Try CLOB first
            resp = self.client.clob.session.get(
                f"{self.client.clob.host}/balance-allowance"
            )
            resp.raise_for_status()
            data = resp.json()
            raw_balance = Decimal(str(data.get("balance", "0")))
        except Exception as e:
            logger.warning(
                "Polymarket: Failed to fetch balance from CLOB: %s. Falling back to on-chain.",
                e,
            )
            raw_balance = Decimal(self.client.get_usdc_balance())

        # USDC on Polygon has 6 decimals
        cash = raw_balance / Decimal("1000000")

        return AccountBalance(
            account_id=self.ACCOUNT_ID,
            net_liquidation=cash,  # Approximated without position valuation for now
            cash=cash,
            buying_power=cash,
            maintenance_margin=Decimal("0.0"),
        )

    async def get_positions(self, account_id: str) -> list[Position]:
        # CLOB fast-path cache as fallback. The true source should be Subgraph.
        # Since we don't have a reliable Subgraph client implemented directly yet, we use CLOB.
        try:
            raw = self.client.get_positions()
            positions = []
            for p in raw:
                q = Decimal(str(p.get("size", "0")))
                if q > 0:
                    positions.append(
                        Position(
                            symbol=Symbol(
                                ticker=p.get("conditionId"),
                                asset_type=AssetType.PREDICTION,
                            ),
                            quantity=q,
                            avg_cost=Decimal(str(p.get("avg_price", "0"))),
                            market_value=q * Decimal(str(p.get("avg_price", "0"))),
                            unrealized_pnl=Decimal("0"),
                            realized_pnl=Decimal("0"),
                        )
                    )
            return positions
        except Exception as e:
            logger.error("Polymarket: Failed to fetch positions: %s", e)
            return []

    async def get_order_history(
        self, account_id: str, filters: OrderHistoryFilter | None = None
    ) -> list[OrderResult]:
        try:
            raw = self.client.get_orders()
            results = []
            for o in raw:
                status_str = str(o.get("status", "")).upper()
                if "MATCHED" in status_str:
                    status = OrderStatus.FILLED
                elif "CANCELLED" in status_str or "EXPIRED" in status_str:
                    status = OrderStatus.CANCELLED
                else:
                    status = OrderStatus.SUBMITTED

                results.append(
                    OrderResult(
                        order_id=o.get("id"),
                        status=status,
                        filled_quantity=Decimal(str(o.get("size_matched", "0"))),
                        avg_fill_price=Decimal(str(o.get("price", "0"))),
                    )
                )
            return results
        except Exception as e:
            logger.error("Polymarket: Failed to fetch order history: %s", e)
            return []


class PolymarketMarketData(MarketDataProvider):
    def __init__(self, data_source: PolymarketDataSource):
        self.ds = data_source

    def _quote_from_book(self, symbol: Symbol, token_id: str) -> Quote:
        book = self.ds.client.get_orderbook(token_id)

        bid = Decimal("0")
        ask = Decimal("1")
        if book.get("bids"):
            bid = Decimal(str(book["bids"][0]["price"]))
        if book.get("asks"):
            ask = Decimal(str(book["asks"][0]["price"]))

        return Quote(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=bid,  # Approximate fallback
            timestamp=None,
        )

    async def get_quote(self, symbol: Symbol) -> Quote:
        if symbol.asset_type != AssetType.PREDICTION:
            return Quote(symbol=symbol, bid=None, ask=None, last=None)
        token_id = self.ds.resolve_token_id(symbol.ticker, "YES")
        if not token_id:
            return Quote(symbol=symbol, bid=None, ask=None, last=None)
        return self._quote_from_book(symbol, token_id)

    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]:
        res: list[Quote] = []
        for s in symbols:
            q = await self.get_quote(s)
            res.append(q)
        return res

    async def stream_quotes(
        self, symbols: list[Symbol], callback: Callable[[Quote], object]
    ) -> None:
        while True:
            for symbol in symbols:
                q = await self.get_quote(symbol)
                callback(q)
            await asyncio.sleep(5.0)

    async def get_historical(
        self, symbol: Symbol, timeframe: str, period: str
    ) -> list[Bar]:
        return []

    async def get_contract_details(self, symbol: Symbol) -> "ContractDetails":
        from datetime import datetime
        from broker.models import ContractDetails as _CD

        try:
            market = await asyncio.to_thread(self.ds.client.get_market, symbol.ticker)
        except Exception as exc:
            logger.warning("get_contract_details failed for %s: %s", symbol.ticker, exc)
            return _CD(symbol=symbol)
        expires_at = None
        end_date = market.get("end_date_iso", "") or ""
        if end_date:
            try:
                expires_at = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except ValueError:
                pass
        return _CD(
            symbol=symbol,
            long_name=market.get("question", symbol.ticker),
            expires_at=expires_at,
        )

    async def get_options_chain(
        self, symbol: Symbol, expiry: str | None = None
    ) -> OptionsChain:
        return OptionsChain(symbol=symbol)


class PolymarketOrderManager(OrderManager):
    def __init__(
        self, client: PolymarketClient, data_source: PolymarketDataSource, dry_run: bool
    ):
        self.client = client
        self.ds = data_source
        self.dry_run = dry_run
        self._order_update_callbacks: list[Callable[[OrderResult], object]] = []

    def on_order_update(self, callback: Callable[[OrderResult], object]) -> None:
        self._order_update_callbacks.append(callback)

    async def place_order(self, account_id: str, order: OrderBase) -> OrderResult:
        if isinstance(order, MarketOrder):
            raise ValueError("Polymarket CLOB does not support MarketOrders.")

        if not isinstance(order, LimitOrder):
            raise ValueError(f"Unsupported order type: {type(order)}")

        if self.dry_run:
            logger.info(
                "Polymarket [DRY-RUN]: Would place LimitOrder %s for %s",
                order.side.value,
                order.symbol.ticker,
            )
            import uuid

            return OrderResult(
                order_id=f"dry-run-{uuid.uuid4()}",
                status=OrderStatus.SUBMITTED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
            )

        token_id = self.ds.resolve_token_id(order.symbol.ticker, "YES")
        if not token_id:
            raise ValueError(f"Cannot resolve YES token ID for {order.symbol.ticker}")

        side = BUY if order.side == OrderSide.BUY else SELL
        size = float(order.quantity)
        price = float(order.limit_price)

        # Py-clob-client uses OrderArgs inside create_order
        from py_clob_client.clob_types import OrderArgs

        args = OrderArgs(size=size, price=price, side=side, token_id=token_id)

        try:
            resp = self.client.clob.create_order(args)
            if resp.get("success"):
                return OrderResult(
                    order_id=resp.get("orderID"),
                    status=OrderStatus.SUBMITTED,
                    filled_quantity=Decimal("0"),
                    avg_fill_price=Decimal("0"),
                )
            else:
                return OrderResult(
                    order_id="rejected",
                    status=OrderStatus.REJECTED,
                    filled_quantity=Decimal("0"),
                    avg_fill_price=Decimal("0"),
                    message=resp.get("errorMsg", "Unknown SDK error"),
                )
        except Exception as e:
            return OrderResult(
                order_id="failed",
                status=OrderStatus.REJECTED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
                message=str(e),
            )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        raise NotImplementedError(
            "Polymarket does not support modifying orders. Cancel and submit a new one."
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        if self.dry_run:
            logger.info("Polymarket [DRY-RUN]: Would cancel order %s", order_id)
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
            )
        try:
            resp = self.client.cancel_order(order_id)
            if resp.get("success", False):
                return OrderResult(
                    order_id=order_id,
                    status=OrderStatus.CANCELLED,
                    filled_quantity=Decimal("0"),
                    avg_fill_price=Decimal("0"),
                )
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
                message=resp.get("errorMsg", "Cancel failed"),
            )
        except Exception:
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                filled_quantity=Decimal("0"),
                avg_fill_price=Decimal("0"),
            )

    async def get_order_status(self, order_id: str) -> OrderStatus:
        try:
            for o in self.client.get_orders():
                if str(o.get("id")) != order_id:
                    continue
                status_str = str(o.get("status", "")).upper()
                if "MATCHED" in status_str:
                    return OrderStatus.FILLED
                if "CANCELLED" in status_str or "EXPIRED" in status_str:
                    return OrderStatus.CANCELLED
                if "REJECT" in status_str:
                    return OrderStatus.REJECTED
                return OrderStatus.SUBMITTED
        except Exception:
            pass
        return OrderStatus.SUBMITTED

    async def cancel_all_orders(self) -> None:
        pass  # Polymarket does not support bulk cancellation


class PolymarketBroker(Broker):
    def __init__(
        self,
        client: PolymarketClient,
        data_source: PolymarketDataSource,
        creds_path: str,
        dry_run: bool,
    ):
        self._conn = PolymarketConnection(client, creds_path, dry_run)
        self._acct = PolymarketAccount(client)
        self._data = PolymarketMarketData(data_source)
        self._om = PolymarketOrderManager(client, data_source, dry_run)

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
        return BrokerCapabilities(stocks=False, options=False, prediction_markets=True)
