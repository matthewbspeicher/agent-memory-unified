from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from typing import Optional

from broker.models import AccountBalance, OrderBase, Position, Quote


@dataclass
class RiskResult:
    passed: bool
    rule_name: str = ""
    reason: str = ""
    adjusted_quantity: Optional[Decimal] = None


@dataclass
class PortfolioContext:
    positions: list[Position]
    balance: AccountBalance
    daily_pnl: Decimal = Decimal("0")
    daily_trade_count: int = 0
    sectors: dict[str, Decimal] = field(default_factory=dict)  # sector → market value
    external_positions: list[dict] = field(default_factory=list)
    external_balances: list[dict] = field(default_factory=list)
    price_histories: dict[str, list[Decimal]] = field(
        default_factory=dict
    )  # ticker -> price series


class RiskRule(ABC):
    name: str

    @abstractmethod
    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult: ...


class MaxPositionSize(RiskRule):
    name = "max_position_size"

    def __init__(self, max_dollars: float, max_shares: int) -> None:
        self.max_dollars = Decimal(str(max_dollars))
        self.max_shares = Decimal(str(max_shares))

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        from broker.models import OrderSide

        symbol_ticker = trade.symbol.ticker
        ibkr_qty = next(
            (p.quantity for p in ctx.positions if p.symbol.ticker == symbol_ticker),
            Decimal("0"),
        )
        external_qty = sum(
            Decimal(str(p.get("quantity", 0)))
            for p in ctx.external_positions
            if p.get("symbol") == symbol_ticker
        )
        total_qty = ibkr_qty + external_qty
        # SELLs reduce exposure; BUYs increase it
        side = getattr(trade, "side", None)
        if side == OrderSide.SELL:
            projected_qty = total_qty - trade.quantity
        else:
            projected_qty = total_qty + trade.quantity
        if projected_qty > self.max_shares:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Total quantity {projected_qty} exceeds max shares {self.max_shares}",
            )
        trade_value = trade.quantity * (quote.last or Decimal("0"))
        if trade_value > self.max_dollars:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Trade value ${trade_value:.2f} exceeds max dollars ${self.max_dollars}",
            )
        return RiskResult(passed=True, rule_name=self.name)


class MaxPredictionExposure(RiskRule):
    name = "max_prediction_exposure"

    def __init__(self, max_dollars: float) -> None:
        self.max_dollars = Decimal(str(max_dollars))

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        from broker.models import AssetType, OrderSide

        if trade.symbol.asset_type != AssetType.PREDICTION:
            return RiskResult(passed=True, rule_name=self.name)

        symbol_ticker = trade.symbol.ticker
        ibkr_qty = next(
            (p.quantity for p in ctx.positions if p.symbol.ticker == symbol_ticker),
            Decimal("0"),
        )
        external_qty = sum(
            Decimal(str(p.get("quantity", 0)))
            for p in ctx.external_positions
            if p.get("symbol") == symbol_ticker
        )
        total_qty = ibkr_qty + external_qty

        # SELLs reduce exposure; BUYs increase it
        side = getattr(trade, "side", None)
        if side == OrderSide.SELL:
            projected_qty = total_qty - trade.quantity
        else:
            projected_qty = total_qty + trade.quantity

        projected_exposure = projected_qty * (quote.last or Decimal("0"))

        if projected_exposure > self.max_dollars:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Prediction exposure ${projected_exposure:.2f} exceeds max ${self.max_dollars}",
            )
        return RiskResult(passed=True, rule_name=self.name)


class MaxPortfolioExposure(RiskRule):
    name = "max_portfolio_exposure"

    def __init__(self, max_percent: float) -> None:
        self.max_percent = Decimal(str(max_percent))

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        trade_value = trade.quantity * (quote.last or Decimal("0"))
        ibkr_net_liq = ctx.balance.net_liquidation
        external_value = sum(
            Decimal(str(b.get("net_liquidation", 0))) for b in ctx.external_balances
        )
        total_portfolio = ibkr_net_liq + external_value
        if total_portfolio == 0:
            return RiskResult(
                passed=False, rule_name=self.name, reason="Portfolio value is zero"
            )
        exposure = (trade_value / total_portfolio) * 100
        if exposure > self.max_percent:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Exposure {exposure:.1f}% exceeds max {self.max_percent}%",
            )
        return RiskResult(passed=True, rule_name=self.name)


class MaxDailyLoss(RiskRule):
    name = "max_daily_loss"

    def __init__(self, max_dollars: float, action: str = "") -> None:
        self.max_dollars = Decimal(str(max_dollars))
        self.action = action  # "kill_switch" to trigger kill switch

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        if ctx.daily_pnl < -self.max_dollars:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Daily loss ${-ctx.daily_pnl:.2f} exceeds max ${self.max_dollars}",
            )
        return RiskResult(passed=True, rule_name=self.name)


class MaxOpenPositions(RiskRule):
    name = "max_open_positions"

    def __init__(self, max_count: int) -> None:
        self.max_count = max_count

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        if len(ctx.positions) >= self.max_count:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Open positions {len(ctx.positions)} >= max {self.max_count}",
            )
        return RiskResult(passed=True, rule_name=self.name)


class MaxDailyTrades(RiskRule):
    name = "max_daily_trades"

    def __init__(self, max_count: int) -> None:
        self.max_count = max_count

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        if ctx.daily_trade_count >= self.max_count:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Daily trades {ctx.daily_trade_count} >= max {self.max_count}",
            )
        return RiskResult(passed=True, rule_name=self.name)


class SectorConcentration(RiskRule):
    name = "sector_concentration"

    def __init__(self, max_percent: float) -> None:
        self.max_percent = Decimal(str(max_percent))

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        portfolio_value = ctx.balance.net_liquidation
        if portfolio_value == 0:
            return RiskResult(
                passed=False, rule_name=self.name, reason="Portfolio value is zero"
            )
        for sector, value in ctx.sectors.items():
            concentration = (value / portfolio_value) * 100
            if concentration > self.max_percent:
                return RiskResult(
                    passed=False,
                    rule_name=self.name,
                    reason=f"Sector '{sector}' at {concentration:.1f}% exceeds max {self.max_percent}%",
                )
        return RiskResult(passed=True, rule_name=self.name)


class MaxComboDelta(RiskRule):
    name = "max_combo_delta"

    def __init__(self, max_abs_delta: float) -> None:
        self.max_abs_delta = Decimal(str(max_abs_delta))

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        from broker.models import ComboOrder, OrderSide
        from risk.greeks import estimate_option_delta

        delta = Decimal("0")
        if isinstance(trade, ComboOrder):
            current_price = (
                quote.last if quote.last else (quote.ask or quote.bid or Decimal("0"))
            )
            if current_price == 0:
                return RiskResult(
                    passed=False,
                    rule_name=self.name,
                    reason="Cannot estimate Delta: no underlying price",
                )

            for leg in trade.legs:
                if (
                    not leg.symbol.strike
                    or not leg.symbol.right
                    or not leg.symbol.expiry
                ):
                    return RiskResult(
                        passed=False,
                        rule_name=self.name,
                        reason="Missing option details for Delta estimation",
                    )

                leg_delta = estimate_option_delta(
                    current_price,
                    leg.symbol.strike,
                    leg.symbol.right,
                    leg.symbol.expiry,
                )
                # Option delta is usually per share. Total delta = delta * ratio * quantity * multiplier
                # For standard limits, often limit is placed on position delta (e.g. 100 shares = 100 delta)
                multiplier = (
                    Decimal(str(leg.symbol.multiplier))
                    if leg.symbol.multiplier
                    else Decimal("100")
                )
                position_delta = (
                    leg_delta * Decimal(str(leg.ratio)) * trade.quantity * multiplier
                )

                if leg.side == OrderSide.SELL:
                    position_delta = -position_delta

                delta += position_delta

        if abs(delta) > self.max_abs_delta:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Estimated absolute Delta {abs(delta):.2f} exceeds max {self.max_abs_delta}",
            )
        return RiskResult(passed=True, rule_name=self.name)


class MaxDrawdownPct(RiskRule):
    name = "max_drawdown_pct"

    def __init__(self, max_pct: float, action: str = "") -> None:
        self.max_pct = Decimal(str(max_pct))
        self.action = action
        self.high_water_mark = Decimal("0")

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        portfolio_value = ctx.balance.net_liquidation
        if portfolio_value <= 0:
            return RiskResult(passed=True, rule_name=self.name)

        if portfolio_value > self.high_water_mark:
            self.high_water_mark = portfolio_value

        drawdown_pct = (
            (self.high_water_mark - portfolio_value) / self.high_water_mark
        ) * Decimal("100")

        if drawdown_pct > self.max_pct:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Drawdown {drawdown_pct:.1f}% exceeds max {self.max_pct}% (HWM: ${self.high_water_mark:.2f})",
            )

        return RiskResult(passed=True, rule_name=self.name)


class MaxCorrelation(RiskRule):
    name = "max_correlation"

    def __init__(self, max_avg: float) -> None:
        self.max_avg = float(max_avg)

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        # Expected `ctx.sectors` or a new field `ctx.price_histories` dict[str, list[Decimal]]
        # populated by the calling Agent (since the synchronous evaluate cannot fetch historical data)
        histories = getattr(ctx, "price_histories", None)
        if not histories or len(histories) < 2:
            return RiskResult(passed=True, rule_name=self.name)

        from risk.correlation import avg_portfolio_correlation

        avg_corr = avg_portfolio_correlation(histories)

        if avg_corr > self.max_avg:
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Average portfolio correlation {avg_corr:.2f} exceeds max {self.max_avg:.2f}",
            )

        return RiskResult(passed=True, rule_name=self.name)
