from __future__ import annotations
import logging
from datetime import date
from decimal import Decimal

from broker.interfaces import AccountProvider
from broker.models import (
    Account,
    AccountBalance,
    AssetType,
    OptionRight,
    OrderHistoryFilter,
    OrderResult,
    OrderStatus,
    Position,
    Symbol,
)
from adapters.tradier.client import TradierClient
from adapters.tradier._status import STATUS_MAP as _STATUS_MAP

logger = logging.getLogger(__name__)


def parse_occ_symbol(occ: str) -> Symbol:
    """Parse OCC option symbol like 'AAPL210917C00145000' into a Symbol."""
    # Format: SYMBOL + YYMMDD + C/P + STRIKE*1000 (8 digits)
    # Find where the date starts (first digit after the root symbol)
    i = 0
    while i < len(occ) and not occ[i].isdigit():
        i += 1
    root = occ[:i]
    rest = occ[i:]
    if len(rest) < 15:
        return Symbol(ticker=occ, asset_type=AssetType.OPTION)

    yy, mm, dd = rest[0:2], rest[2:4], rest[4:6]
    right_char = rest[6]
    strike_raw = rest[7:15]

    return Symbol(
        ticker=root,
        asset_type=AssetType.OPTION,
        expiry=date(2000 + int(yy), int(mm), int(dd)),
        right=OptionRight.CALL if right_char == "C" else OptionRight.PUT,
        strike=Decimal(strike_raw) / 1000,
        multiplier=100,
    )


class TradierAccountProvider(AccountProvider):
    def __init__(self, client: TradierClient) -> None:
        self._client = client

    async def get_accounts(self) -> list[Account]:
        return [Account(account_id=self._client.account_id)]

    async def get_positions(self, account_id: str) -> list[Position]:
        raw = await self._client.get_positions()
        positions = []
        for p in raw:
            symbol_str = p.get("symbol", "")
            # Detect option positions by length/format
            if len(symbol_str) > 10 and any(c in symbol_str for c in "CP"):
                symbol = parse_occ_symbol(symbol_str)
            else:
                symbol = Symbol(ticker=symbol_str)

            positions.append(
                Position(
                    symbol=symbol,
                    quantity=Decimal(str(p.get("quantity", 0))),
                    avg_cost=Decimal(str(p.get("cost_basis", 0)))
                    / max(Decimal(str(abs(p.get("quantity", 1)))), Decimal("1")),
                    market_value=Decimal(
                        "0"
                    ),  # Tradier doesn't return market_value in positions
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=Decimal("0"),
                )
            )
        return positions

    async def get_balances(self, account_id: str) -> AccountBalance:
        raw = await self._client.get_balances()
        bal = raw.get("balances", raw)
        return AccountBalance(
            account_id=account_id,
            net_liquidation=Decimal(str(bal.get("total_equity", 0))),
            buying_power=Decimal(
                str(bal.get("option_buying_power", bal.get("stock_buying_power", 0)))
            ),
            cash=Decimal(str(bal.get("total_cash", 0))),
            maintenance_margin=Decimal(str(bal.get("maintenance_requirement", 0))),
        )

    async def get_order_history(
        self,
        account_id: str,
        filters: OrderHistoryFilter | None = None,
    ) -> list[OrderResult]:
        raw = await self._client.get_orders()
        results = []
        for o in raw:
            status_str = o.get("status", "").lower()
            results.append(
                OrderResult(
                    order_id=str(o.get("id", "")),
                    status=_STATUS_MAP.get(status_str, OrderStatus.SUBMITTED),
                    filled_quantity=Decimal(
                        str(o.get("exec_quantity", o.get("quantity", 0)))
                    ),
                    avg_fill_price=Decimal(str(o["avg_fill_price"]))
                    if o.get("avg_fill_price")
                    else None,
                )
            )
        return results
