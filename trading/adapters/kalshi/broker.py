"""
KalshiBroker — implements the Broker interface for Kalshi prediction markets.

Probability representation: Kalshi uses integer cents (0–100). Internally we
convert cents → Decimal (0.00–1.00) when returning Quote objects so that
agent thresholds and risk rules stay in natural probability space.

Order mapping:
  BUY  side  → buy YES contracts (bet the event happens)
  SELL side  → buy NO contracts  (bet the event does NOT happen)
  LimitOrder.limit_price is treated as a 0–1 probability (e.g. 0.65 = 65¢)
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from broker.interfaces import (
    AccountProvider, BrokerConnection, Broker,
    MarketDataProvider, OrderManager,
)
from broker.models import (
    Account, AccountBalance, Bar, BrokerCapabilities,
    ContractDetails, LimitOrder, OptionsChain, OrderBase,
    OrderHistoryFilter, OrderResult, OrderStatus, OrderSide,
    Position, Quote, Symbol, AssetType,
)
from adapters.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)


def _cents_to_prob(cents: int | None) -> Decimal | None:
    if cents is None:
        return None
    return Decimal(str(cents)) / Decimal("100")


def _prob_to_cents(prob: Decimal) -> int:
    clamped = max(Decimal("1"), min(Decimal("99"), prob * 100))
    return int(clamped.to_integral_value())


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class KalshiConnection(BrokerConnection):
    def __init__(self, client: KalshiClient, market_data: KalshiMarketData) -> None:
        self._client = client
        self._market_data = market_data
        self._connected = False
        self._callbacks: list[Callable[[], Any]] = []

    async def connect(self) -> None:
        try:
            await self._client.get_balance()
            self._connected = True
            logger.info("Kalshi: connected successfully")
            self._market_data.start_streaming()
        except Exception as exc:
            logger.warning("Kalshi: connection check failed (read-only public data still available): %s", exc)
            self._connected = True  # public market data still works

    async def disconnect(self) -> None:
        await self._client.close()
        self._connected = False
        for cb in self._callbacks:
            cb()

    def is_connected(self) -> bool:
        return self._connected

    def on_disconnected(self, callback: Callable[[], Any]) -> None:
        self._callbacks.append(callback)

    async def reconnect(self) -> None:
        await self.connect()


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

class KalshiAccount(AccountProvider):
    ACCOUNT_ID = "KALSHI"

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def get_accounts(self) -> list[Account]:
        return [Account(account_id=self.ACCOUNT_ID, account_type="prediction_market")]

    async def get_balances(self, account_id: str) -> AccountBalance:
        data = await self._client.get_balance()
        # Kalshi returns balance in cents (integer)
        available_cents = data.get("available_balance", 0)
        total_cents = data.get("portfolio_value", available_cents)
        factor = Decimal("0.01")
        net_liq = Decimal(str(total_cents)) * factor
        cash = Decimal(str(available_cents)) * factor
        return AccountBalance(
            account_id=self.ACCOUNT_ID,
            net_liquidation=net_liq,
            buying_power=cash,
            cash=cash,
            maintenance_margin=Decimal("0"),
        )

    async def get_positions(self, account_id: str) -> list[Position]:
        raw = await self._client.get_positions()
        positions: list[Position] = []
        for p in raw:
            ticker = p.get("ticker", "")
            qty = Decimal(str(p.get("position", 0)))
            if qty == 0:
                continue
            # market_exposure is current value of position in cents
            mv_cents = Decimal(str(p.get("market_exposure", 0)))
            avg_price_cents = Decimal(str(p.get("fees_paid", 0)))  # best proxy available
            total_traded_cents = Decimal(str(p.get("total_traded", 0)))
            avg_cost = (total_traded_cents / qty / 100) if qty else Decimal("0")
            market_value = mv_cents * Decimal("0.01")
            unrealized = market_value - (avg_cost * qty)
            positions.append(Position(
                symbol=Symbol(ticker=ticker, asset_type=AssetType.PREDICTION),
                quantity=qty,
                avg_cost=avg_cost,
                market_value=market_value,
                unrealized_pnl=unrealized,
                realized_pnl=Decimal("0"),
            ))
        return positions

    async def get_order_history(
        self, account_id: str, filters: OrderHistoryFilter | None = None,
    ) -> list[OrderResult]:
        raw = await self._client.get_order_history()
        results: list[OrderResult] = []
        for o in raw:
            status_str = o.get("status", "")
            status = {
                "executed": OrderStatus.FILLED,
                "canceled": OrderStatus.CANCELLED,
                "pending": OrderStatus.SUBMITTED,
                "partially_filled": OrderStatus.PARTIAL,
                "resting": OrderStatus.SUBMITTED,
            }.get(status_str, OrderStatus.SUBMITTED)
            results.append(OrderResult(
                order_id=o.get("order_id", ""),
                status=status,
                filled_quantity=Decimal(str(o.get("contracts_filled", 0))),
                avg_fill_price=_cents_to_prob(o.get("avg_price")),
            ))
        return results


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

class KalshiMarketData(MarketDataProvider):
    def __init__(self, client: KalshiClient) -> None:
        self._client = client
        self._ob_cache: dict[str, Quote] = {}
        self._callbacks: list[Callable[[Quote], Any]] = []
        self._ws_task = None

    def _on_ws_message(self, msg: dict) -> None:
        if msg.get("type") == "ticker":
            data = msg.get("msg", {})
            ticker = data.get("market_ticker")
            if not ticker: return
            
            q = Quote(
                symbol=Symbol(ticker=ticker, asset_type=AssetType.PREDICTION),
                bid=_cents_to_prob(data.get("yes_bid")),
                ask=_cents_to_prob(data.get("yes_ask")),
                last=_cents_to_prob(data.get("price")),
                volume=data.get("volume", 0)
            )
            self._ob_cache[ticker] = q
            for cb in self._callbacks:
                cb(q)

    def start_streaming(self) -> None:
        import asyncio
        if self._ws_task is None:
            self._ws_task = asyncio.create_task(
                self._client.ws_connect(channels=["ticker"], callback=self._on_ws_message)
            )

    async def get_quote(self, symbol: Symbol) -> Quote:
        if symbol.ticker in self._ob_cache:
            return self._ob_cache[symbol.ticker]
            
        ob = await self._client.get_orderbook(symbol.ticker)
        yes_bids = ob.get("yes", [])
        yes_asks = ob.get("no", [])  # NO side is effectively YES ask
        bid = _cents_to_prob(yes_bids[0][0] if yes_bids else None)
        # NO best bid → implied YES ask = 100 - no_bid
        ask_cents = (100 - yes_asks[0][0]) if yes_asks else None
        ask = _cents_to_prob(ask_cents)
        trades = await self._client.get_trades(symbol.ticker, limit=1)
        last = _cents_to_prob(trades[0].get("yes_price") if trades else None)
        volume = sum(t.get("count", 0) for t in trades)
        return Quote(symbol=symbol, bid=bid, ask=ask, last=last, volume=volume)

    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]:
        results = []
        for sym in symbols:
            try:
                results.append(await self.get_quote(sym))
            except Exception as exc:
                logger.warning("Kalshi get_quote failed for %s: %s", sym.ticker, exc)
        return results

    async def stream_quotes(
        self, symbols: list[Symbol], callback: Callable[[Quote], Any],
    ) -> None:
        self._callbacks.append(callback)
        self.start_streaming()
        import asyncio
        while True:
            await asyncio.sleep(86400)

    async def get_historical(self, symbol: Symbol, timeframe: str, period: str) -> list[Bar]:
        # Kalshi historical price data not yet exposed via v2 REST
        return []

    async def get_options_chain(self, symbol: Symbol, expiry: str | None = None) -> OptionsChain:
        raise NotImplementedError("Kalshi does not support options chains")

    async def get_contract_details(self, symbol: Symbol) -> ContractDetails:
        from datetime import datetime, timezone
        data = await self._client.get_market(symbol.ticker)
        expires_at = None
        close_ts = data.get("close_time") or data.get("expected_expiration_time") or ""
        if close_ts:
            try:
                expires_at = datetime.fromisoformat(close_ts.replace("Z", "+00:00"))
            except ValueError:
                pass
        return ContractDetails(
            symbol=symbol,
            long_name=data.get("title", symbol.ticker),
            category=data.get("category", ""),
            expires_at=expires_at,
        )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class KalshiOrderManager(OrderManager):
    def __init__(self, client: KalshiClient) -> None:
        self._client = client
        self._callbacks: list[Callable[[OrderResult], Any]] = []

    async def place_order(self, account_id: str, order: OrderBase) -> OrderResult:
        if not isinstance(order, LimitOrder):
            raise ValueError(
                "Kalshi only supports limit orders. "
                "Pass a LimitOrder with limit_price as a 0–1 probability."
            )
        side = "yes" if order.side == OrderSide.BUY else "no"
        price_cents = _prob_to_cents(order.limit_price)
        count = int(order.quantity)
        try:
            raw = await self._client.create_order(
                ticker=order.symbol.ticker,
                side=side,
                count=count,
                price=price_cents,
            )
            status_str = raw.get("status", "resting")
            status = OrderStatus.SUBMITTED if "rest" in status_str else OrderStatus.FILLED
            fill_qty = Decimal(str(raw.get("contracts_filled", 0)))
            avg_fill = _cents_to_prob(raw.get("avg_price"))
            result = OrderResult(
                order_id=raw.get("order_id", ""),
                status=status,
                filled_quantity=fill_qty,
                avg_fill_price=avg_fill,
            )
        except Exception as exc:
            result = OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                message=str(exc),
            )
        for cb in self._callbacks:
            cb(result)
        return result

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        raise NotImplementedError("Kalshi does not support order modification; cancel and re-submit")

    async def cancel_order(self, order_id: str) -> OrderResult:
        raw = await self._client.cancel_order(order_id)
        return OrderResult(
            order_id=order_id,
            status=OrderStatus.CANCELLED,
            message=raw.get("status"),
        )

    async def get_order_status(self, order_id: str) -> OrderStatus:
        data = await self._client.get_order_history(limit=200)
        for o in data:
            if o.get("order_id") == order_id:
                s = o.get("status", "")
                if s == "executed":
                    return OrderStatus.FILLED
                if s == "canceled":
                    return OrderStatus.CANCELLED
        return OrderStatus.SUBMITTED

    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None:
        self._callbacks.append(callback)

    async def cancel_all_orders(self) -> None:
        pass  # Kalshi does not support bulk cancellation


# ---------------------------------------------------------------------------
# Composite Broker
# ---------------------------------------------------------------------------

class KalshiBroker(Broker):
    """Full Broker implementation backed by Kalshi's REST API."""

    def __init__(
        self,
        key_id: str | None = None,
        private_key_path: str | None = None,
        demo: bool = True,
    ) -> None:
        self._client = KalshiClient(
            key_id=key_id,
            private_key_path=private_key_path,
            demo=demo,
        )
        self._market_data = KalshiMarketData(self._client)
        self._connection = KalshiConnection(self._client, self._market_data)
        self._account = KalshiAccount(self._client)
        self._orders = KalshiOrderManager(self._client)

    @property
    def connection(self) -> KalshiConnection:
        return self._connection

    @property
    def account(self) -> KalshiAccount:
        return self._account

    @property
    def market_data(self) -> KalshiMarketData:
        return self._market_data

    @property
    def orders(self) -> KalshiOrderManager:
        return self._orders

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            stocks=False,
            options=False,
            futures=False,
            forex=False,
            bonds=False,
            streaming=False,
            prediction_markets=True,
        )
