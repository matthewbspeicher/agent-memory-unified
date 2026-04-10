"""TaoshiBacktestEngine — replays historical Taoshi positions through the consensus pipeline."""

from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from broker.models import Bar, OrderSide
from data.signal_bus import SignalBus
from backtesting.models import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    TradeRecord,
)
from backtesting.engine import SimulatedPortfolio, _apply_slippage, _get_commission_fn
from backtesting.replay import HistoricalReplay
from backtesting.taoshi_replay import TaoshiSignalReplay
from backtesting.results import apply_metrics
from integrations.bittensor.consensus_aggregator import MinerConsensusAggregator
from strategies.bittensor_consensus import BittensorAlphaAgent

logger = logging.getLogger(__name__)


class TaoshiBacktestEngine:
    """Specialized engine for replaying Bittensor miner signals."""

    def __init__(self, taoshi_root: str) -> None:
        self.taoshi_root = taoshi_root

    async def run(
        self,
        config: BacktestConfig,
        historical_data: dict[str, list[Bar]],
    ) -> BacktestResult:
        result = BacktestResult(
            config=config,
            status=BacktestStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        try:
            # 1. Initialize Replay Sources
            bar_replay = HistoricalReplay.from_bars_dict(historical_data)
            signal_replay = TaoshiSignalReplay(self.taoshi_root)

            if len(bar_replay) == 0:
                raise ValueError("No historical bar data provided")

            # 2. Initialize Pipeline
            signal_bus = SignalBus()
            aggregator = MinerConsensusAggregator(
                signal_bus, window_minutes=60
            )  # 1h window

            # Create BittensorAlphaAgent
            from agents.models import AgentConfig, ActionLevel

            agent_cfg = AgentConfig(
                name="bittensor_alpha_backtest",
                strategy="bittensor_alpha",
                schedule="on_demand",
                action_level=ActionLevel.SUGGEST_TRADE,
                parameters=config.metadata.get("agent_parameters", {}),
            )
            agent = BittensorAlphaAgent(agent_cfg)
            agent.signal_bus = signal_bus
            await agent.setup()

            # Start aggregator
            await aggregator.start()

            # 3. Setup Portfolio
            portfolio = SimulatedPortfolio(config.initial_capital)
            commission_fn = _get_commission_fn(
                config.commission, config.commission_params
            )

            # Track open trades per (agent, symbol) for exit logic
            open_trades: dict[tuple[str, str], TradeRecord] = {}

            bar_count = 0
            total_bars = len(bar_replay)

            logger.info(
                "Starting Taoshi backtest: %d bars, %d signals",
                total_bars,
                len(signal_replay),
            )

            while True:
                bars = bar_replay.advance()
                if bars is None:
                    break

                bar_count += 1
                current_ts = list(bars.values())[0].timestamp
                current_prices = {ticker: bar.close for ticker, bar in bars.items()}

                # Record equity
                portfolio.record_equity(current_ts, current_prices)

                # Update aggregator time
                aggregator.set_reference_time(current_ts)

                # --- Signal Injection ---
                # Get signals that happened before or at this bar's timestamp
                signals = signal_replay.get_signals_before(current_ts)
                for signal in signals:
                    await signal_bus.publish(signal)

                # --- Strategy Execution ---
                # BittensorAlphaAgent handles signals asynchronously and populates _pending_opportunities
                opportunities = await agent.scan(
                    None
                )  # DataBus not needed for this agent

                for opp in opportunities:
                    if not opp.suggested_trade:
                        continue

                    trade = opp.suggested_trade
                    ticker = trade.symbol.ticker
                    bar = bars.get(ticker)
                    if not bar:
                        continue

                    side = "BUY" if trade.side == OrderSide.BUY else "SELL"
                    fill_price = _apply_slippage(bar.close, side, config.slippage_bps)
                    qty = trade.quantity

                    # Backtest sizing fallback: use fixed allocation if qty is 0
                    if qty == 0:
                        equity = portfolio.current_equity(current_prices)
                        risk_per_trade = equity * Decimal("0.05")  # 5% risk
                        qty = risk_per_trade / fill_price

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

                    # Execute (Open new or add to existing)
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

                # Progress logging
                if bar_count % max(total_bars // 10, 1) == 0:
                    logger.info("Backtest: %d/%d bars", bar_count, total_bars)

            # Close any remaining positions at last price
            last_prices: dict[str, Decimal] = (
                {t: bar.close for t, bar in bars.items()} if bars else {}
            )
            for key, trade in list(open_trades.items()):
                ticker = trade.symbol.ticker
                if ticker in portfolio.positions:
                    last_price = (
                        last_prices.get(ticker, trade.entry_price)
                        if trade.entry_price
                        else Decimal("0")
                    )
                    close_side = "SELL" if trade.side == "BUY" else "BUY"
                    portfolio.close_position(
                        ticker,
                        close_side,
                        abs(portfolio.positions[ticker].quantity),
                        last_price,
                        Decimal("0"),
                        current_ts,
                    )

            # --- Finalize ---
            result.trades = portfolio.trades
            result.equity_curve = portfolio.equity_history
            result.status = BacktestStatus.COMPLETED
            result.completed_at = datetime.now(timezone.utc)

            apply_metrics(result)
            logger.info(
                "Backtest complete. Trades: %d, Return: %.2f%%",
                len(result.trades),
                result.total_return_pct,
            )

        except Exception as e:
            result.status = BacktestStatus.FAILED
            result.error = str(e)
            logger.error("Taoshi backtest failed: %s", e, exc_info=True)

        return result
