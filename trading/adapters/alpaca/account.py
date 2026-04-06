from __future__ import annotations
import logging
from decimal import Decimal

from broker.interfaces import AccountProvider
from broker.models import (
    Account,
    AccountBalance,
    OrderHistoryFilter,
    OrderResult,
    OrderStatus,
    Position,
    Symbol,
)
from adapters.alpaca.client import AlpacaClient
from adapters.alpaca._status import STATUS_MAP as _STATUS_MAP

logger = logging.getLogger(__name__)


class AlpacaAccountProvider(AccountProvider):
    def __init__(self, client: AlpacaClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    async def get_accounts(self) -> list[Account]:
        return [Account(account_id=self._account_id)]

    async def get_positions(self, account_id: str) -> list[Position]:
        raw = await self._client.get_positions()
        return [
            Position(
                symbol=Symbol(ticker=p["symbol"]),
                quantity=Decimal(p["qty"]),
                avg_cost=Decimal(p["avg_entry_price"]),
                market_value=Decimal(p["market_value"]),
                unrealized_pnl=Decimal(p["unrealized_pl"]),
                realized_pnl=Decimal("0"),
            )
            for p in raw
        ]

    async def get_balances(self, account_id: str) -> AccountBalance:
        raw = await self._client.get_account()
        return AccountBalance(
            account_id=account_id,
            net_liquidation=Decimal(raw["equity"]),
            buying_power=Decimal(raw["buying_power"]),
            cash=Decimal(raw["cash"]),
            maintenance_margin=Decimal(raw.get("maintenance_margin", "0")),
        )

    async def get_order_history(
        self,
        account_id: str,
        filters: OrderHistoryFilter | None = None,
    ) -> list[OrderResult]:
        status = "all"
        if filters and filters.status:
            status = filters.status.value.lower()
        raw = await self._client.get_orders(status=status)
        return [_to_order_result(o) for o in raw]


def _to_order_result(raw: dict) -> OrderResult:
    return OrderResult(
        order_id=raw["id"],
        status=_STATUS_MAP.get(raw.get("status", ""), OrderStatus.SUBMITTED),
        filled_quantity=Decimal(raw.get("filled_qty", "0")),
        avg_fill_price=Decimal(raw["filled_avg_price"])
        if raw.get("filled_avg_price")
        else None,
    )
