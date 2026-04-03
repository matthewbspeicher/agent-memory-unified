from decimal import Decimal

from ib_async import IB

from broker.interfaces import AccountProvider
from broker.models import (
    Account, AccountBalance, OrderHistoryFilter, OrderResult, Position,
)
from adapters.ibkr.symbols import from_contract
from adapters.ibkr.orders import to_order_result


class IBKRAccountProvider(AccountProvider):
    def __init__(self, ib: IB):
        self._ib = ib

    async def get_accounts(self) -> list[Account]:
        accounts = self._ib.managedAccounts()
        return [Account(account_id=a) for a in accounts]

    async def get_positions(self, account_id: str) -> list[Position]:
        ib_positions = self._ib.positions(account_id)
        return [
            Position(
                symbol=from_contract(p.contract),
                quantity=Decimal(str(p.position)),
                avg_cost=Decimal(str(p.avgCost)),
                market_value=Decimal(str(p.marketValue)) if hasattr(p, "marketValue") else Decimal("0"),
                unrealized_pnl=Decimal(str(p.unrealizedPNL)) if hasattr(p, "unrealizedPNL") else Decimal("0"),
                realized_pnl=Decimal(str(p.realizedPNL)) if hasattr(p, "realizedPNL") else Decimal("0"),
            )
            for p in ib_positions
        ]

    async def get_balances(self, account_id: str) -> AccountBalance:
        summary = self._ib.accountSummary(account_id)
        values = {item.tag: Decimal(item.value) for item in summary if item.value}
        return AccountBalance(
            account_id=account_id,
            net_liquidation=values.get("NetLiquidation", Decimal("0")),
            buying_power=values.get("BuyingPower", Decimal("0")),
            cash=values.get("TotalCashValue", Decimal("0")),
            maintenance_margin=values.get("MaintMarginReq", Decimal("0")),
        )

    async def get_order_history(
        self, account_id: str, filters: OrderHistoryFilter | None = None,
    ) -> list[OrderResult]:
        trades = self._ib.trades()
        results = [to_order_result(t) for t in trades]
        if filters:
            if filters.status:
                results = [r for r in results if r.status == filters.status]
        return results
