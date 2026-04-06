"""Performance metrics calculation for backtest results."""

from __future__ import annotations
import math
from decimal import Decimal
from typing import Any

from backtesting.models import BacktestResult, EquityPoint, TradeRecord


def compute_metrics(result: BacktestResult) -> dict[str, Any]:
    """Compute all performance metrics from trade records and equity curve."""
    trades = result.trades
    equity_curve = result.equity_curve
    config = result.config

    if not equity_curve:
        return _empty_metrics()

    # Basic trade stats
    closed_trades = [t for t in trades if t.is_closed]
    total_trades = len(closed_trades)
    winning = [t for t in closed_trades if t.pnl > 0]
    losing = [t for t in closed_trades if t.pnl < 0]

    # Equity-based metrics
    equities = [ep.equity for ep in equity_curve]
    initial_equity = equities[0] if equities else config.initial_capital
    final_equity = equities[-1] if equities else config.initial_capital

    total_return_pct = (
        float((final_equity - initial_equity) / initial_equity * 100)
        if initial_equity
        else 0.0
    )

    # Annualized return
    if len(equity_curve) >= 2:
        first_ts = equity_curve[0].timestamp
        last_ts = equity_curve[-1].timestamp
        days = max((last_ts - first_ts).days, 1)
        years = days / 365.25
        if years > 0 and initial_equity > 0:
            annualized_return_pct = float(
                (float(final_equity / initial_equity) ** (1 / years) - 1) * 100
            )
        else:
            annualized_return_pct = total_return_pct
    else:
        annualized_return_pct = total_return_pct

    # Sharpe ratio
    returns = _compute_returns(equities)
    sharpe = _compute_sharpe(returns, config.risk_free_rate)

    # Sortino ratio (uses downside deviation only)
    sortino = _compute_sortino(returns, config.risk_free_rate)

    # Max drawdown
    max_dd_pct, max_dd_duration = _compute_max_drawdown(equity_curve)

    # Win rate
    win_rate = len(winning) / total_trades * 100 if total_trades else 0.0

    # Profit factor
    gross_profit = sum(t.pnl for t in winning) if winning else Decimal("0")
    gross_loss = abs(sum(t.pnl for t in losing)) if losing else Decimal("1")
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # Trade averages
    avg_pnl = (
        sum(t.pnl for t in closed_trades) / total_trades
        if total_trades
        else Decimal("0")
    )
    avg_win = sum(t.pnl for t in winning) / len(winning) if winning else Decimal("0")
    avg_loss = sum(t.pnl for t in losing) / len(losing) if losing else Decimal("0")
    largest_win = max((t.pnl for t in winning), default=Decimal("0"))
    largest_loss = min((t.pnl for t in losing), default=Decimal("0"))
    avg_holding = (
        sum(t.holding_bars for t in closed_trades) / total_trades
        if total_trades
        else 0.0
    )
    total_commission = sum(t.commission for t in trades)

    # Per-agent metrics
    agent_metrics = _compute_agent_metrics(closed_trades, initial_equity)

    return {
        "total_return_pct": round(total_return_pct, 4),
        "annualized_return_pct": round(annualized_return_pct, 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "max_drawdown_duration_bars": max_dd_duration,
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 4),
        "total_trades": total_trades,
        "avg_trade_pnl": avg_pnl,
        "avg_winning_trade": avg_win,
        "avg_losing_trade": avg_loss,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "avg_holding_bars": round(avg_holding, 1),
        "total_commission": total_commission,
        "final_equity": final_equity,
        "final_cash": equity_curve[-1].cash if equity_curve else config.initial_capital,
        "agent_metrics": agent_metrics,
    }


def apply_metrics(result: BacktestResult) -> BacktestResult:
    """Compute and apply metrics to a BacktestResult in-place."""
    metrics = compute_metrics(result)
    for key, value in metrics.items():
        if hasattr(result, key):
            setattr(result, key, value)
    return result


def _compute_returns(equities: list[Decimal]) -> list[float]:
    """Compute period-over-period returns."""
    returns = []
    for i in range(1, len(equities)):
        if equities[i - 1] and equities[i - 1] != 0:
            ret = float((equities[i] - equities[i - 1]) / equities[i - 1])
            returns.append(ret)
    return returns


def _compute_sharpe(returns: list[float], risk_free_rate: float) -> float:
    """Compute annualized Sharpe ratio."""
    if not returns or len(returns) < 2:
        return 0.0

    avg_return = sum(returns) / len(returns)
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance) if variance > 0 else 0.0

    if std_dev == 0:
        return 0.0

    # Annualize: assume 252 trading days
    daily_rf = risk_free_rate / 252
    sharpe = (avg_return - daily_rf) / std_dev * math.sqrt(252)
    return sharpe


def _compute_sortino(returns: list[float], risk_free_rate: float) -> float:
    """Compute annualized Sortino ratio (downside deviation only)."""
    if not returns or len(returns) < 2:
        return 0.0

    avg_return = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]

    if not downside:
        return float("inf") if avg_return > 0 else 0.0

    downside_var = sum(r**2 for r in downside) / len(returns)  # use total periods
    downside_dev = math.sqrt(downside_var) if downside_var > 0 else 0.0

    if downside_dev == 0:
        return 0.0

    daily_rf = risk_free_rate / 252
    sortino = (avg_return - daily_rf) / downside_dev * math.sqrt(252)
    return sortino


def _compute_max_drawdown(equity_curve: list[EquityPoint]) -> tuple[float, int]:
    """Compute maximum drawdown percentage and duration in bars."""
    if not equity_curve:
        return 0.0, 0

    peak = equity_curve[0].equity
    max_dd = Decimal("0")
    max_dd_duration = 0
    current_dd_duration = 0

    for point in equity_curve:
        if point.equity >= peak:
            peak = point.equity
            current_dd_duration = 0
        else:
            current_dd_duration += 1
            dd = (peak - point.equity) / peak * 100 if peak else Decimal("0")
            if dd > max_dd:
                max_dd = dd
                max_dd_duration = current_dd_duration

    return float(max_dd), max_dd_duration


def _compute_agent_metrics(
    trades: list[TradeRecord], initial_equity: Decimal
) -> dict[str, dict[str, Any]]:
    """Compute per-agent performance breakdown."""
    by_agent: dict[str, list[TradeRecord]] = {}
    for t in trades:
        by_agent.setdefault(t.agent_name, []).append(t)

    metrics = {}
    for agent_name, agent_trades in by_agent.items():
        winning = [t for t in agent_trades if t.pnl > 0]
        losing = [t for t in agent_trades if t.pnl < 0]
        total_pnl = sum(t.pnl for t in agent_trades)
        gross_profit = sum(t.pnl for t in winning) if winning else Decimal("0")
        gross_loss = abs(sum(t.pnl for t in losing)) if losing else Decimal("1")

        metrics[agent_name] = {
            "total_trades": len(agent_trades),
            "win_rate": round(len(winning) / len(agent_trades) * 100, 2)
            if agent_trades
            else 0.0,
            "total_pnl": str(total_pnl),
            "avg_pnl": str(total_pnl / len(agent_trades)) if agent_trades else "0",
            "profit_factor": round(float(gross_profit / gross_loss), 4)
            if gross_loss > 0
            else float("inf"),
            "best_trade": str(max((t.pnl for t in agent_trades), default=Decimal("0"))),
            "worst_trade": str(
                min((t.pnl for t in agent_trades), default=Decimal("0"))
            ),
            "symbols_traded": list(set(t.symbol for t in agent_trades)),
        }

    return metrics


def _empty_metrics() -> dict[str, Any]:
    return {
        "total_return_pct": 0.0,
        "annualized_return_pct": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "max_drawdown_pct": 0.0,
        "max_drawdown_duration_bars": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_trades": 0,
        "avg_trade_pnl": Decimal("0"),
        "avg_winning_trade": Decimal("0"),
        "avg_losing_trade": Decimal("0"),
        "largest_win": Decimal("0"),
        "largest_loss": Decimal("0"),
        "avg_holding_bars": 0.0,
        "total_commission": Decimal("0"),
        "final_equity": Decimal("0"),
        "final_cash": Decimal("0"),
        "agent_metrics": {},
    }
