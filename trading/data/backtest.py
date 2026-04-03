from __future__ import annotations
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from agents.base import Agent
from agents.models import Opportunity
from broker.models import (
    AccountBalance, Bar, Position, Quote, Symbol, OrderSide, OrderBase, OrderResult, OrderStatus
)
from data.bus import DataBus
from data.sources.base import DataSource

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    agent_name: str
    parameters: dict[str, Any]
    sharpe_ratio: float
    profit_factor: float
    total_pnl: Decimal
    max_drawdown: float
    win_rate: float
    total_trades: int
    run_date: datetime
    data_start: date
    data_end: date

    def is_deployable(self, min_sharpe: float = 1.0, min_trades: int = 50) -> bool:
        """Check if this strategy meets minimum deployment thresholds."""
        return self.total_trades >= min_trades and self.sharpe_ratio >= min_sharpe


def score_backtest_run(
    *,
    agent_name: str,
    parameters: dict[str, Any],
    snapshots: list[dict[str, Any]],
    initial_equity: Decimal,
    final_equity: Decimal,
) -> BacktestResult:
    total_pnl = final_equity - initial_equity

    equities = [float(s["equity"]) for s in snapshots]
    daily_returns = [
        (equities[i] - equities[i - 1]) / equities[i - 1]
        for i in range(1, len(equities))
    ]

    if len(daily_returns) > 1:
        mean_r = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
        std_r = math.sqrt(variance)
        sharpe_ratio = (mean_r / std_r * math.sqrt(252)) if std_r != 0 else 0.0
    elif len(daily_returns) == 1:
        sharpe_ratio = 0.0
    else:
        sharpe_ratio = 0.0

    peak = equities[0] if equities else 0.0
    max_drawdown = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        if peak > 0:
            drawdown = (peak - eq) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    wins = sum(1 for r in daily_returns if r > 0)
    win_rate = wins / len(daily_returns) if daily_returns else 0.0

    gains = sum(r for r in daily_returns if r > 0)
    losses = sum(r for r in daily_returns if r < 0)
    profit_factor = gains / abs(losses) if losses != 0 else float("inf")

    total_trades = sum(s["executed"] for s in snapshots)

    times = [s["time"] for s in snapshots]
    data_start = min(times).date()
    data_end = max(times).date()

    return BacktestResult(
        agent_name=agent_name,
        parameters=parameters,
        sharpe_ratio=sharpe_ratio,
        profit_factor=profit_factor,
        total_pnl=total_pnl,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        total_trades=total_trades,
        run_date=datetime.now(timezone.utc),
        data_start=data_start,
        data_end=data_end,
    )


class HistoricalDataSource(DataSource):
    """
    Provides pre-loaded historical data, replaying it up to exactly a simulated `current_time`.
    """
    name = "historical_replay"
    supports_quotes = True
    supports_historical = True

    def __init__(self, bars: dict[str, list[Bar]]) -> None:
        self.bars = bars
        self.current_time: datetime | None = None

    async def get_quote(self, symbol: Symbol) -> Quote:
        if not self.current_time:
            raise ValueError("current_time not set")

        sym_bars = self.bars.get(symbol.ticker, [])
        valid_bars = [b for b in sym_bars if b.timestamp <= self.current_time]
        if not valid_bars:
            raise ValueError(f"No historical data for {symbol.ticker} at {self.current_time}")

        last_bar = valid_bars[-1]
        return Quote(
            symbol=symbol,
            bid=last_bar.close - Decimal("0.01"),
            ask=last_bar.close + Decimal("0.01"),
            last=last_bar.close,
            volume=last_bar.volume,
            timestamp=last_bar.timestamp
        )

    # Approximate trading-day counts for common period strings
    _PERIOD_BARS: dict[str, int] = {
        "1mo": 21, "3mo": 63, "6mo": 126, "1y": 252, "2y": 504, "5y": 1260,
    }

    async def get_historical(
        self, symbol: Symbol, timeframe: str = "1d", period: str = "max"
    ) -> list[Bar]:
        if not self.current_time:
            raise ValueError("current_time not set")
        sym_bars = self.bars.get(symbol.ticker, [])
        visible = [b for b in sym_bars if b.timestamp <= self.current_time]
        # Trim to match requested period (prevents look-ahead bias)
        max_bars = self._PERIOD_BARS.get(period)
        if max_bars is not None and len(visible) > max_bars:
            visible = visible[-max_bars:]
        return visible

    async def get_options_chain(self, symbol: Symbol) -> Any:
        raise NotImplementedError("Historical options not supported in replay")


async def load_replay_source(
    symbols: list[Symbol],
    timeframe: str = "1d",
    period: str = "1mo",
) -> HistoricalDataSource:
    """
    Convenience helper to fetch historical data for multiple symbols 
    and wrap it in a HistoricalDataSource for replay.
    """
    from data.sources.broker_data import BrokerHistoricalSource
    source = BrokerHistoricalSource()
    
    bars_map: dict[str, list[Bar]] = {}
    for sym in symbols:
        bars = await source.get_historical(sym, timeframe=timeframe, period=period)
        bars_map[sym.ticker] = bars
        
    return HistoricalDataSource(bars_map)


class ReplayDataBus(DataBus):
    """
    A specialized DataBus for backtesting. 
    It mocks position tracking, cash balance, and uses the HistoricalDataSource 
    for limited data visibility based on current_time.
    """
    def __init__(self, historical_source: HistoricalDataSource, starting_balance: Decimal = Decimal("100000.0")) -> None:
        super().__init__(sources=[historical_source], broker=None)
        self.historical_source = historical_source
        self.current_time: datetime | None = None

        self._mock_cash = starting_balance
        self._mock_positions: dict[str, Position] = {}

    def advance_time(self, new_time: datetime) -> None:
        self.current_time = new_time
        self.historical_source.current_time = new_time
        self._cache.clear()

    async def get_positions(self) -> list[Position]:
        # Recalculate PNL dynamically
        for pos in self._mock_positions.values():
            try:
                quote = await self.get_quote(pos.symbol)
                last_price = quote.last or Decimal("0")
                if last_price > 0:
                    market_val = pos.quantity * last_price
                    cost_basis = pos.quantity * pos.avg_cost
                    # Data classes are frozen, so we must recreate
                    self._mock_positions[pos.symbol.ticker] = Position(
                        symbol=pos.symbol,
                        quantity=pos.quantity,
                        avg_cost=pos.avg_cost,
                        market_value=market_val,
                        unrealized_pnl=market_val - cost_basis,
                        realized_pnl=pos.realized_pnl
                    )
            except Exception:
                pass
        return list(self._mock_positions.values())

    async def get_balances(self) -> AccountBalance:
        pos_value = Decimal("0")
        for pos in await self.get_positions():
            pos_value += pos.market_value

        return AccountBalance(
            account_id="backtest",
            net_liquidation=self._mock_cash + pos_value,
            buying_power=self._mock_cash * 2,
            cash=self._mock_cash,
            maintenance_margin=Decimal("0")
        )

    async def get_recent_trades(self, limit: int = 100) -> list[dict]:
        return []

    async def get_all_positions(self, exclude_accounts: list[str] | None = None) -> list:
        return await self.get_positions()

    async def get_sector(self, symbol: Symbol) -> str | None:
        return "Technology"


class BacktestEngine:
    """
    Drives a ReplayDataBus and a set of Agents through a historical timeline.
    Simulates trades generated by opportunities.
    """
    def __init__(self, bus: ReplayDataBus, agents: list[Agent]) -> None:
        self.bus = bus
        self.agents = agents
        self.history: list[dict[str, Any]] = []

    async def run(self, times: list[datetime]) -> dict[str, Any]:
        logger.info(f"Starting backtest over {len(times)} periods")
        initial_balances = await self.bus.get_balances()
        initial_equity = initial_balances.net_liquidation

        for t in times:
            self.bus.advance_time(t)

            total_opportunities = []
            for agent in self.agents:
                try:
                    opps = await agent.scan(self.bus)
                    total_opportunities.extend(opps)
                except Exception as e:
                    logger.error(f"Agent {agent.name} failed at {t}: {e}")

            executed = await self.simulate_execution(total_opportunities, t)

            bals = await self.bus.get_balances()
            self.history.append({
                "time": t,
                "cash": bals.cash,
                "equity": bals.net_liquidation,
                "opportunities": len(total_opportunities),
                "executed": len(executed)
            })

        final_balances = await self.bus.get_balances()
        return {
            "initial_equity": initial_equity,
            "final_equity": final_balances.net_liquidation,
            "snapshots": self.history
        }

    async def simulate_execution(self, opportunities: list[Opportunity], t: datetime) -> list[Opportunity]:
        executed = []
        for opp in opportunities:
            if not opp.suggested_trade:
                continue
            
            trade: OrderBase = opp.suggested_trade
            try:
                quote = await self.bus.get_quote(trade.symbol)
                price = quote.last or Decimal("0")
                if price <= 0:
                    continue

                if trade.side == OrderSide.BUY:
                    cost = price * trade.quantity
                    if self.bus._mock_cash >= cost:
                        self.bus._mock_cash -= cost
                        tkr = trade.symbol.ticker
                        if tkr in self.bus._mock_positions:
                            pos = self.bus._mock_positions[tkr]
                            new_q = pos.quantity + trade.quantity
                            new_cost = (pos.quantity * pos.avg_cost) + cost
                            self.bus._mock_positions[tkr] = Position(
                                symbol=trade.symbol,
                                quantity=new_q,
                                avg_cost=new_cost / new_q,
                                market_value=new_q * price,
                                unrealized_pnl=(new_q * price) - new_cost,
                                realized_pnl=pos.realized_pnl
                            )
                        else:
                            self.bus._mock_positions[tkr] = Position(
                                symbol=trade.symbol,
                                quantity=trade.quantity,
                                avg_cost=price,
                                market_value=cost,
                                unrealized_pnl=Decimal("0"),
                                realized_pnl=Decimal("0")
                            )
                        executed.append(opp)

                elif trade.side == OrderSide.SELL:
                    tkr = trade.symbol.ticker
                    if tkr in self.bus._mock_positions:
                        pos = self.bus._mock_positions[tkr]
                        if pos.quantity >= trade.quantity:
                            revenue = price * trade.quantity
                            self.bus._mock_cash += revenue
                            new_q = pos.quantity - trade.quantity
                            
                            # calculate realized pnl
                            cost_basis_sold = pos.avg_cost * trade.quantity
                            realized = revenue - cost_basis_sold

                            if new_q == Decimal("0"):
                                del self.bus._mock_positions[tkr]
                            else:
                                new_cost = pos.avg_cost * new_q
                                self.bus._mock_positions[tkr] = Position(
                                    symbol=trade.symbol,
                                    quantity=new_q,
                                    avg_cost=pos.avg_cost,
                                    market_value=new_q * price,
                                    unrealized_pnl=(new_q * price) - new_cost,
                                    realized_pnl=pos.realized_pnl + realized
                                )
                            executed.append(opp)
            except Exception as e:
                logger.warning(f"Failed to execute opp for {trade.symbol.ticker}: {e}")

        return executed


@dataclass
class SimulatedFill:
    """Result of a simulated order fill."""
    price: Decimal
    quantity: Decimal
    fees: Decimal


@dataclass
class BacktestTrade:
    """A single simulated trade with P&L."""
    symbol: str
    side: str
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_time: datetime
    exit_time: datetime
    fees: Decimal = Decimal("0")

    @property
    def pnl(self) -> Decimal:
        if self.side == "BUY":
            return (self.exit_price - self.entry_price) * self.quantity - self.fees
        return (self.entry_price - self.exit_price) * self.quantity - self.fees

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0


class FillSimulator:
    """Simulates order fills with configurable slippage and fees."""

    def __init__(
        self,
        slippage_pct: Decimal = Decimal("0.001"),
        fee_per_trade: Decimal = Decimal("1.00"),
    ) -> None:
        self.slippage_pct = slippage_pct
        self.fee_per_trade = fee_per_trade

    def simulate(
        self,
        order: OrderBase,
        bar_close: Decimal,
        bar_low: Decimal | None = None,
        bar_high: Decimal | None = None,
    ) -> "SimulatedFill | None":
        from broker.models import LimitOrder as LO

        if isinstance(order, LO):
            return self._fill_limit(order, bar_close, bar_low, bar_high)
        return self._fill_market(order, bar_close)

    def _fill_market(self, order: OrderBase, bar_close: Decimal) -> "SimulatedFill":
        if order.side == OrderSide.BUY:
            price = bar_close * (1 + self.slippage_pct)
        else:
            price = bar_close * (1 - self.slippage_pct)
        return SimulatedFill(
            price=price.quantize(Decimal("0.01")),
            quantity=order.quantity,
            fees=self.fee_per_trade,
        )

    def _fill_limit(
        self,
        order: OrderBase,
        bar_close: Decimal,
        bar_low: Decimal | None,
        bar_high: Decimal | None,
    ) -> "SimulatedFill | None":
        from broker.models import LimitOrder as LO
        limit = order.limit_price  # type: ignore[attr-defined]
        if order.side == OrderSide.BUY:
            low = bar_low if bar_low is not None else bar_close
            if low <= limit:
                return SimulatedFill(price=limit, quantity=order.quantity, fees=self.fee_per_trade)
            return None
        else:
            high = bar_high if bar_high is not None else bar_close
            if high >= limit:
                return SimulatedFill(price=limit, quantity=order.quantity, fees=self.fee_per_trade)
            return None
