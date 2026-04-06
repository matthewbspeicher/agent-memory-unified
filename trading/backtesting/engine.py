"""BacktestEngine — simulates agent strategies against historical market data."""

from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from broker.models import (
    Bar,
    Quote,
    Symbol,
    OrderSide,
)
from backtesting.models import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    TradeRecord,
    EquityPoint,
    CommissionModel,
)
from backtesting.replay import HistoricalReplay
from backtesting.results import apply_metrics

logger = logging.getLogger(__name__)


class SimulatedPortfolio:
    """Paper portfolio for backtesting — tracks cash, positions, and P&L."""

    def __init__(self, initial_capital: Decimal) -> None:
        self.cash: Decimal = initial_capital
        self.positions: dict[str, _Position] = {}  # ticker -> position
        self.trades: list[TradeRecord] = []
        self.equity_history: list[EquityPoint] = []
        self._commission_total: Decimal = Decimal("0")

    def current_equity(self, current_prices: dict[str, Decimal]) -> Decimal:
        positions_value = sum(
            pos.quantity * current_prices.get(pos.symbol, pos.avg_cost)
            for pos in self.positions.values()
        )
        return self.cash + positions_value

    def record_equity(self, timestamp: datetime, prices: dict[str, Decimal]) -> None:
        equity = self.current_equity(prices)
        positions_value = sum(
            pos.quantity * prices.get(pos.symbol, pos.avg_cost)
            for pos in self.positions.values()
        )
        self.equity_history.append(
            EquityPoint(
                timestamp=timestamp,
                equity=equity,
                cash=self.cash,
                positions_value=positions_value,
            )
        )

    def open_position(
        self,
        ticker: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal,
        trade_id: str,
        agent_name: str,
        signal: str,
        reasoning: str,
        timestamp: datetime,
    ) -> None:
        """Open or add to a position."""
        notional = quantity * price
        cost = notional + commission
        self.cash -= cost if side == "BUY" else -cost
        self._commission_total += commission

        pos = self.positions.get(ticker)
        if pos is None:
            self.positions[ticker] = _Position(
                symbol=ticker,
                quantity=quantity if side == "BUY" else -quantity,
                avg_cost=price,
            )
        else:
            # Average cost calculation
            if side == "BUY":
                total_cost = pos.quantity * pos.avg_cost + quantity * price
                new_qty = pos.quantity + quantity
                pos.avg_cost = total_cost / new_qty if new_qty else Decimal("0")
                pos.quantity = new_qty
            else:
                pos.quantity -= quantity

        self.trades.append(
            TradeRecord(
                id=trade_id,
                agent_name=agent_name,
                symbol=ticker,
                side=side,
                entry_time=timestamp,
                entry_price=price,
                quantity=quantity,
                commission=commission,
                signal=signal,
                reasoning=reasoning,
            )
        )

    def close_position(
        self,
        ticker: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal,
        timestamp: datetime,
    ) -> TradeRecord | None:
        """Close or reduce a position. Returns the matching trade record if found."""
        pos = self.positions.get(ticker)
        if pos is None:
            return None

        close_qty = min(quantity, abs(pos.quantity))
        notional = close_qty * price
        self.cash += (
            notional - commission if side == "SELL" else -(notional + commission)
        )
        self._commission_total += commission

        # Find matching open trade for P&L calculation
        matching_trade = None
        for t in reversed(self.trades):
            if t.symbol == ticker and t.side != side and t.is_closed is False:
                matching_trade = t
                break

        if matching_trade and matching_trade.entry_price:
            pnl_per_share = (
                (price - matching_trade.entry_price)
                if side == "SELL"
                else (matching_trade.entry_price - price)
            )
            total_pnl = pnl_per_share * close_qty - commission
            pnl_pct = (
                float(pnl_per_share / matching_trade.entry_price * 100)
                if matching_trade.entry_price
                else 0.0
            )

            # Update the original trade
            matching_trade.exit_time = timestamp
            matching_trade.exit_price = price
            matching_trade.pnl = total_pnl
            matching_trade.pnl_pct = pnl_pct
            matching_trade.holding_bars = 1  # simplified

        # Update position
        pos.quantity -= close_qty if side == "SELL" else -close_qty
        if pos.quantity == 0:
            del self.positions[ticker]

        return matching_trade

    @property
    def commission_total(self) -> Decimal:
        return self._commission_total


class _Position:
    __slots__ = ("symbol", "quantity", "avg_cost")

    def __init__(self, symbol: str, quantity: Decimal, avg_cost: Decimal):
        self.symbol = symbol
        self.quantity = quantity
        self.avg_cost = avg_cost


class BacktestEngine:
    """Orchestrates a backtest: replays historical data, feeds agents, simulates fills."""

    def __init__(self) -> None:
        self._results: dict[str, BacktestResult] = {}

    async def run(
        self,
        config: BacktestConfig,
        agents: list[Any],  # list of StructuredAgent instances
        historical_data: dict[str, list[Bar]],  # ticker -> bars
        data_bus: Any | None = None,  # optional DataBus for agent scan() calls
    ) -> BacktestResult:
        """Run a backtest and return results."""
        result = BacktestResult(
            config=config,
            status=BacktestStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        try:
            replay = HistoricalReplay.from_bars_dict(historical_data)
            if len(replay) == 0:
                raise ValueError("No historical data provided")

            # Apply warmup offset
            start_idx = min(config.warmup_bars, len(replay) - 1)
            replay.seek(start_idx)

            portfolio = SimulatedPortfolio(config.initial_capital)
            commission_fn = _get_commission_fn(
                config.commission, config.commission_params
            )

            # Track open trades per (agent, symbol) for exit logic
            open_trades: dict[tuple[str, str], TradeRecord] = {}

            bar_count = 0
            total_bars = len(replay) - start_idx

            while True:
                bars = replay.advance()
                if bars is None:
                    break

                bar_count += 1
                current_ts = list(bars.values())[0].timestamp
                current_prices = {ticker: bar.close for ticker, bar in bars.items()}

                # Record equity
                portfolio.record_equity(current_ts, current_prices)

                # Build a mock DataBus if none provided
                mock_bus = _MockDataBus(bars, historical_data, data_bus)

                # Run each agent's scan
                for agent in agents:
                    try:
                        opportunities = await agent.scan(mock_bus)
                    except Exception as e:
                        logger.warning(
                            "Agent %s scan failed at bar %d: %s",
                            agent.name,
                            bar_count,
                            e,
                        )
                        continue

                    for opp in opportunities:
                        if not opp.suggested_trade:
                            continue

                        trade = opp.suggested_trade
                        ticker = trade.symbol.ticker
                        bar = bars.get(ticker)
                        if not bar:
                            continue

                        side = "BUY" if trade.side == OrderSide.BUY else "SELL"
                        fill_price = _apply_slippage(
                            bar.close, side, config.slippage_bps
                        )
                        qty = trade.quantity

                        # Calculate commission
                        commission = commission_fn(qty, fill_price, trade.symbol)

                        trade_id = str(uuid.uuid4())
                        key = (agent.name, ticker)

                        # Check if we need to close existing position first
                        existing = portfolio.positions.get(ticker)
                        if existing and existing.quantity != 0:
                            # If direction changed, close first
                            if (side == "BUY" and existing.quantity < 0) or (
                                side == "SELL" and existing.quantity > 0
                            ):
                                close_side = "SELL" if existing.quantity > 0 else "BUY"
                                close_qty = abs(existing.quantity)
                                portfolio.close_position(
                                    ticker,
                                    close_side,
                                    close_qty,
                                    fill_price,
                                    commission_fn(close_qty, fill_price, trade.symbol),
                                    current_ts,
                                )
                                open_trades.pop(key, None)

                        # Open new position
                        portfolio.open_position(
                            ticker=ticker,
                            side=side,
                            quantity=qty,
                            price=fill_price,
                            commission=commission,
                            trade_id=trade_id,
                            agent_name=agent.name,
                            signal=opp.signal,
                            reasoning=opp.reasoning,
                            timestamp=current_ts,
                        )
                        open_trades[key] = portfolio.trades[-1]

                        logger.debug(
                            "Backtest trade: %s %s %s @ %s (bar %d/%d)",
                            agent.name,
                            side,
                            ticker,
                            fill_price,
                            bar_count,
                            total_bars,
                        )

                # Progress logging every 10%
                if bar_count % max(total_bars // 10, 1) == 0:
                    pct = bar_count / total_bars * 100
                    logger.info(
                        "Backtest progress: %.0f%% (%d/%d bars)",
                        pct,
                        bar_count,
                        total_bars,
                    )

                # Replay speed throttling
                if config.replay_speed > 0:
                    await asyncio.sleep(config.replay_speed)

            # Close any remaining positions at last price
            last_prices = {t: bar.close for t, bar in bars.items()} if bars else {}
            for key, trade in list(open_trades.items()):
                ticker = trade.symbol
                if ticker in portfolio.positions:
                    last_price = last_prices.get(ticker, trade.entry_price)
                    close_side = "SELL" if trade.side.value == "BUY" else "BUY"
                    portfolio.close_position(
                        ticker,
                        close_side,
                        abs(portfolio.positions[ticker].quantity),
                        last_price,
                        Decimal("0"),
                        current_ts,
                    )

            # Build result
            result.trades = portfolio.trades
            result.equity_curve = portfolio.equity_history
            result.status = BacktestStatus.COMPLETED
            result.completed_at = datetime.now(timezone.utc)

            # Compute metrics
            apply_metrics(result)

        except Exception as e:
            result.status = BacktestStatus.FAILED
            result.completed_at = datetime.now(timezone.utc)
            result.error = str(e)
            logger.error("Backtest failed: %s", e, exc_info=True)

        self._results[config.name] = result
        return result

    def get_result(self, name: str) -> BacktestResult | None:
        return self._results.get(name)

    def list_results(self) -> list[str]:
        return list(self._results.keys())


# --- Helpers ---


def _apply_slippage(price: Decimal, side: str, slippage_bps: float) -> Decimal:
    """Apply slippage to a fill price."""
    if slippage_bps <= 0:
        return price
    factor = Decimal(str(slippage_bps / 10000))
    if side == "BUY":
        return price * (Decimal("1") + factor)
    else:
        return price * (Decimal("1") - factor)


def _get_commission_fn(model: CommissionModel, params: dict) -> Any:
    """Return a commission calculation function."""
    if model == CommissionModel.ZERO:
        return lambda qty, price, symbol: Decimal("0")
    elif model == CommissionModel.FLAT_PER_SHARE:
        rate = Decimal(str(params.get("per_share", 0.005)))
        return lambda qty, price, symbol: rate * qty
    elif model == CommissionModel.FLAT_PER_CONTRACT:
        rate = Decimal(str(params.get("per_contract", 0.65)))
        return lambda qty, price, symbol: rate * qty
    elif model == CommissionModel.PERCENT_OF_NOTIONAL:
        rate = Decimal(str(params.get("percent", 0.001)))
        return lambda qty, price, symbol: qty * price * rate
    elif model == CommissionModel.FIDELITY:
        from broker.models import FidelityFeeModel, OrderBase, OrderSide

        fm = FidelityFeeModel()

        def _fidelity(qty, price, symbol):
            # Construct a temporary order for the fee model
            order = OrderBase(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=qty,
                account_id="backtest",
            )
            return fm.calculate(order, price)

        return _fidelity
    elif model == CommissionModel.IBKR:
        from broker.models import IBKRFeeModel, OrderBase, OrderSide

        fm = IBKRFeeModel()

        def _ibkr(qty, price, symbol):
            order = OrderBase(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=qty,
                account_id="backtest",
            )
            return fm.calculate(order, price)

        return _ibkr
    else:
        return lambda qty, price, symbol: Decimal("0")


class _MockDataBus:
    """Minimal DataBus-like object that serves bars from replay to agent scan()."""

    def __init__(
        self,
        current_bars: dict[str, Bar],
        all_bars: dict[str, list[Bar]],
        real_bus=None,
    ):
        self._bars = current_bars
        self._all_bars = all_bars
        self._real_bus = real_bus

    async def get_quote(self, symbol: Symbol) -> Quote:
        bar = self._bars.get(symbol.ticker)
        if bar:
            return Quote(
                symbol=symbol,
                bid=bar.close,
                ask=bar.close,
                last=bar.close,
                volume=bar.volume,
                timestamp=bar.timestamp,
            )
        raise ValueError(f"No bar for {symbol.ticker}")

    async def get_historical(
        self, symbol: Symbol, timeframe: str = "1d", period: str = "3mo"
    ) -> list[Bar]:
        bars = self._all_bars.get(symbol.ticker, [])
        if bars:
            return bars
        raise ValueError(f"No historical data for {symbol.ticker}")

    async def get_rsi(self, symbol: Symbol, period: int = 14) -> float:
        if self._real_bus:
            return await self._real_bus.get_rsi(symbol, period)
        bars = await self.get_historical(symbol)
        from data.indicators import compute_rsi

        return compute_rsi(bars, period)

    async def get_sma(self, symbol: Symbol, period: int = 20) -> float:
        bars = await self.get_historical(symbol)
        from data.indicators import compute_sma

        return compute_sma(bars, period)

    async def get_ema(self, symbol: Symbol, period: int = 20) -> float:
        bars = await self.get_historical(symbol)
        from data.indicators import compute_ema

        return compute_ema(bars, period)

    def get_universe(self, name: str | list[str]) -> list[Symbol]:
        if isinstance(name, list):
            return [Symbol(ticker=t) for t in name]
        return [Symbol(ticker=t) for t in self._bars.keys()]

    async def get_positions(self) -> list:
        return []

    async def get_balances(self) -> None:
        return None
