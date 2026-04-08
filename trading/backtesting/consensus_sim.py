"""ConsensusSimulator — tests multi-agent consensus strategies on historical data.

Wraps the BacktestEngine replay loop with the EnhancedConsensusRouter to simulate
how weighted voting, quorum rules, and regime-aware thresholds affect trading performance.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from broker.models import Bar, Quote, Symbol, OrderSide
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
from agents.consensus import (
    ConsensusConfig,
    EnhancedConsensusRouter,
    AgentWeightProvider,
)

logger = logging.getLogger(__name__)


@dataclass
class ConsensusMetrics:
    """Consensus-specific metrics from a simulation run."""

    total_opportunities: int = 0
    consensus_trades: int = 0
    filtered_trades: int = 0
    consensus_rate: float = 0.0  # percentage of opportunities that reached consensus
    avg_consensus_weight: float = 0.0
    avg_votes_per_consensus: float = 0.0
    total_agents: int = 0

    # Breakdown by regime
    regime_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Weight source used
    weight_source: str = "equal"

    # Config snapshot
    config_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_opportunities": self.total_opportunities,
            "consensus_trades": self.consensus_trades,
            "filtered_trades": self.filtered_trades,
            "consensus_rate": round(self.consensus_rate, 4),
            "avg_consensus_weight": round(self.avg_consensus_weight, 4),
            "avg_votes_per_consensus": round(self.avg_votes_per_consensus, 2),
            "total_agents": self.total_agents,
            "regime_breakdown": self.regime_breakdown,
            "weight_source": self.weight_source,
            "config_snapshot": self.config_snapshot,
        }


@dataclass
class ConsensusSimulationResult:
    """Complete result of a consensus simulation run."""

    backtest_result: BacktestResult
    consensus_metrics: ConsensusMetrics

    def to_dict(self) -> dict[str, Any]:
        d = self.backtest_result.to_dict()
        d["consensus_metrics"] = self.consensus_metrics.to_dict()
        return d


class _SimPortfolio:
    """Paper portfolio for consensus simulation — tracks cash, positions, and P&L."""

    def __init__(self, initial_capital: Decimal) -> None:
        self.cash: Decimal = initial_capital
        self.positions: dict[str, _SimPosition] = {}
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
        notional = quantity * price
        cost = notional + commission
        self.cash -= cost if side == "BUY" else -cost
        self._commission_total += commission

        pos = self.positions.get(ticker)
        if pos is None:
            self.positions[ticker] = _SimPosition(
                symbol=ticker,
                quantity=quantity if side == "BUY" else -quantity,
                avg_cost=price,
            )
        else:
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
        pos = self.positions.get(ticker)
        if pos is None:
            return None

        close_qty = min(quantity, abs(pos.quantity))
        notional = close_qty * price
        self.cash += (
            notional - commission if side == "SELL" else -(notional + commission)
        )
        self._commission_total += commission

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

            matching_trade.exit_time = timestamp
            matching_trade.exit_price = price
            matching_trade.pnl = total_pnl
            matching_trade.pnl_pct = pnl_pct
            matching_trade.holding_bars = 1

        pos.quantity -= close_qty if side == "SELL" else -close_qty
        if pos.quantity == 0:
            del self.positions[ticker]

        return matching_trade

    @property
    def commission_total(self) -> Decimal:
        return self._commission_total


class _SimPosition:
    __slots__ = ("symbol", "quantity", "avg_cost")

    def __init__(self, symbol: str, quantity: Decimal, avg_cost: Decimal):
        self.symbol = symbol
        self.quantity = quantity
        self.avg_cost = avg_cost


class _MockDataBus:
    """Serves bars from replay to agent scan() calls."""

    def __init__(
        self,
        current_bars: dict[str, Bar],
        all_bars: dict[str, list[Bar]],
        real_bus: Any | None = None,
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


def _apply_slippage(price: Decimal, side: str, slippage_bps: float) -> Decimal:
    if slippage_bps <= 0:
        return price
    factor = Decimal(str(slippage_bps / 10000))
    if side == "BUY":
        return price * (Decimal("1") + factor)
    else:
        return price * (Decimal("1") - factor)


def _get_commission_fn(model: CommissionModel, params: dict) -> Any:
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
        from broker.models import FidelityFeeModel, OrderBase, OrderSide as S

        fm_fid = FidelityFeeModel()

        def _fidelity(qty, price, symbol):
            order = OrderBase(
                symbol=symbol, side=S.BUY, quantity=qty, account_id="backtest"
            )
            return fm_fid.calculate(order, price)

        return _fidelity
    elif model == CommissionModel.IBKR:
        from broker.models import IBKRFeeModel, OrderBase, OrderSide as S

        fm_ib = IBKRFeeModel()

        def _ibkr(qty, price, symbol):
            order = OrderBase(
                symbol=symbol, side=S.BUY, quantity=qty, account_id="backtest"
            )
            return fm_ib.calculate(order, price)

        return _ibkr
    else:
        return lambda qty, price, symbol: Decimal("0")


class ConsensusSimulator:
    """Simulates multi-agent consensus on historical data.

    Unlike BacktestEngine (which executes every agent's opportunity immediately),
    ConsensusSimulator collects opportunities from all agents per bar, groups them
    by (symbol, side), and only executes trades that reach consensus via the
    EnhancedConsensusRouter.

    This lets you test how different consensus configurations (thresholds, weight
    sources, regime rules) affect trading performance on historical data.

    Usage:
        consensus_config = ConsensusConfig(
            threshold=2,
            weight_source=WeightSource.COMPOSITE,
            weight_threshold=0.6,
        )

        weight_provider = AgentWeightProvider()
        weight_provider.update_profile(AgentWeightProfile(
            agent_name="momentum",
            sharpe_ratio=1.8,
            elo_rating=1450,
            total_trades=300,
            win_rate=58.0,
        ))

        simulator = ConsensusSimulator(
            consensus_config=consensus_config,
            weight_provider=weight_provider,
        )

        result = await simulator.run(
            backtest_config=config,
            agents=[agent1, agent2, agent3],
            historical_data=bars_dict,
        )
    """

    def __init__(
        self,
        consensus_config: ConsensusConfig | None = None,
        weight_provider: AgentWeightProvider | None = None,
    ) -> None:
        self._consensus_config = consensus_config or ConsensusConfig()
        self._weight_provider = weight_provider or AgentWeightProvider()
        self._router = EnhancedConsensusRouter(
            target_router=None,
            config=self._consensus_config,
            weight_provider=self._weight_provider,
        )

    async def run(
        self,
        backtest_config: BacktestConfig,
        agents: list[Any],
        historical_data: dict[str, list[Bar]],
        data_bus: Any | None = None,
    ) -> ConsensusSimulationResult:
        """Run a consensus simulation on historical data."""
        result = BacktestResult(
            config=backtest_config,
            status=BacktestStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        metrics = ConsensusMetrics(
            weight_source=self._consensus_config.weight_source.value
        )
        metrics.config_snapshot = {
            "threshold": self._consensus_config.threshold,
            "weight_source": self._consensus_config.weight_source.value,
            "weight_threshold": self._consensus_config.weight_threshold,
            "regime_thresholds": self._consensus_config.regime_thresholds,
            "unanimous_regimes": self._consensus_config.unanimous_regimes,
            "min_agents": self._consensus_config.min_agents,
            "window_minutes": self._consensus_config.window_minutes,
        }

        try:
            replay = HistoricalReplay.from_bars_dict(historical_data)
            if len(replay) == 0:
                raise ValueError("No historical data provided")

            start_idx = min(backtest_config.warmup_bars, len(replay) - 1)
            replay.seek(start_idx)

            portfolio = _SimPortfolio(backtest_config.initial_capital)
            commission_fn = _get_commission_fn(
                backtest_config.commission, backtest_config.commission_params
            )

            open_trades: dict[tuple[str, str], TradeRecord] = {}

            bar_count = 0
            total_bars = len(replay) - start_idx
            metrics.total_agents = len(agents)

            while True:
                bars = replay.advance()
                if bars is None:
                    break

                bar_count += 1
                current_ts = list(bars.values())[0].timestamp
                current_prices = {ticker: bar.close for ticker, bar in bars.items()}

                portfolio.record_equity(current_ts, current_prices)

                mock_bus = _MockDataBus(bars, historical_data, data_bus)

                # Collect opportunities from all agents
                all_opportunities: list[Any] = []
                for agent in agents:
                    try:
                        opportunities = await agent.scan(mock_bus)
                        all_opportunities.extend(opportunities)
                    except Exception as e:
                        logger.warning(
                            "Agent %s scan failed at bar %d: %s",
                            agent.name,
                            bar_count,
                            e,
                        )

                # Group by (symbol, side) for consensus checking
                grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
                for opp in all_opportunities:
                    if not opp.suggested_trade:
                        continue
                    trade = opp.suggested_trade
                    ticker = trade.symbol.ticker
                    side = trade.side.value
                    grouped[(ticker, side)].append(opp)

                # Check consensus for each group
                for (ticker, side), opps in grouped.items():
                    bar = bars.get(ticker)
                    if not bar:
                        continue

                    # Extract regime from first opportunity (they share the same bar)
                    regime = self._router._get_regime(opps[0])

                    # Collect votes
                    votes = [
                        self._router.collect_vote(opp, regime=regime) for opp in opps
                    ]
                    metrics.total_opportunities += len(opps)

                    # Check consensus
                    consensus_reached, total_weight, reason = (
                        self._router.check_votes_consensus(votes, regime=regime)
                    )

                    if not consensus_reached:
                        metrics.filtered_trades += len(opps)
                        # Track regime stats for filtered trades
                        regime_key = regime or "unknown"
                        if regime_key not in metrics.regime_breakdown:
                            metrics.regime_breakdown[regime_key] = {
                                "total_opportunities": 0,
                                "consensus_trades": 0,
                                "filtered_trades": 0,
                            }
                        metrics.regime_breakdown[regime_key]["total_opportunities"] += (
                            len(opps)
                        )
                        metrics.regime_breakdown[regime_key]["filtered_trades"] += len(
                            opps
                        )
                        continue

                    # Consensus reached — pick the highest-confidence opportunity
                    # as the representative for execution
                    best_opp = max(opps, key=lambda o: o.confidence)
                    trade = best_opp.suggested_trade
                    side_str = "BUY" if trade.side == OrderSide.BUY else "SELL"
                    fill_price = _apply_slippage(
                        bar.close, side_str, backtest_config.slippage_bps
                    )
                    qty = trade.quantity
                    commission = commission_fn(qty, fill_price, trade.symbol)

                    trade_id = str(uuid.uuid4())
                    key = (best_opp.agent_name, ticker)

                    # Close existing position if direction reversed
                    existing = portfolio.positions.get(ticker)
                    if existing and existing.quantity != 0:
                        if (side_str == "BUY" and existing.quantity < 0) or (
                            side_str == "SELL" and existing.quantity > 0
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

                    # Build consensus reasoning note
                    agent_names = [v.agent_name for v in votes]
                    consensus_note = (
                        f" [Consensus: {len(votes)} agents, weight={total_weight:.2f}"
                        f", agents={','.join(agent_names)}"
                    )
                    if regime:
                        consensus_note += f", regime={regime}"
                    consensus_note += "]"
                    reasoning = best_opp.reasoning + consensus_note

                    portfolio.open_position(
                        ticker=ticker,
                        side=side_str,
                        quantity=qty,
                        price=fill_price,
                        commission=commission,
                        trade_id=trade_id,
                        agent_name="|".join(agent_names),  # mark as consensus trade
                        signal=best_opp.signal,
                        reasoning=reasoning,
                        timestamp=current_ts,
                    )
                    open_trades[key] = portfolio.trades[-1]

                    metrics.consensus_trades += 1
                    metrics.avg_consensus_weight = (
                        metrics.avg_consensus_weight * (metrics.consensus_trades - 1)
                        + total_weight
                    ) / metrics.consensus_trades
                    metrics.avg_votes_per_consensus = (
                        metrics.avg_votes_per_consensus * (metrics.consensus_trades - 1)
                        + len(votes)
                    ) / metrics.consensus_trades

                    # Track regime stats
                    regime_key = regime or "unknown"
                    if regime_key not in metrics.regime_breakdown:
                        metrics.regime_breakdown[regime_key] = {
                            "total_opportunities": 0,
                            "consensus_trades": 0,
                            "filtered_trades": 0,
                        }
                    metrics.regime_breakdown[regime_key]["total_opportunities"] += len(
                        opps
                    )
                    metrics.regime_breakdown[regime_key]["consensus_trades"] += 1

                    logger.debug(
                        "Consensus trade: %s %s @ %s (weight=%.3f, agents=%s, bar %d/%d)",
                        "|".join(agent_names),
                        side_str,
                        ticker,
                        fill_price,
                        total_weight,
                        bar_count,
                        total_bars,
                    )

                # Progress logging every 10%
                if bar_count % max(total_bars // 10, 1) == 0:
                    pct = bar_count / total_bars * 100
                    logger.info(
                        "Consensus simulation progress: %.0f%% (%d/%d bars, %d consensus trades)",
                        pct,
                        bar_count,
                        total_bars,
                        metrics.consensus_trades,
                    )

                if backtest_config.replay_speed > 0:
                    await asyncio.sleep(backtest_config.replay_speed)

            # Close remaining positions at last price
            last_prices = {t: bar.close for t, bar in bars.items()} if bars else {}
            for key, trade in list(open_trades.items()):
                ticker = trade.symbol
                if ticker in portfolio.positions:
                    last_price = last_prices.get(ticker, trade.entry_price)
                    close_side = "SELL" if trade.side == "BUY" else "BUY"
                    portfolio.close_position(
                        ticker,
                        close_side,
                        abs(portfolio.positions[ticker].quantity),
                        last_price,
                        Decimal("0"),
                        current_ts,
                    )

            # Compute consensus metrics
            if metrics.total_opportunities > 0:
                metrics.consensus_rate = (
                    metrics.consensus_trades / metrics.total_opportunities * 100
                )

            # Build result
            result.trades = portfolio.trades
            result.equity_curve = portfolio.equity_history
            result.status = BacktestStatus.COMPLETED
            result.completed_at = datetime.now(timezone.utc)

            # Apply standard backtest metrics
            apply_metrics(result)

        except Exception as e:
            result.status = BacktestStatus.FAILED
            result.completed_at = datetime.now(timezone.utc)
            result.error = str(e)
            logger.error("Consensus simulation failed: %s", e, exc_info=True)

        return ConsensusSimulationResult(
            backtest_result=result,
            consensus_metrics=metrics,
        )
