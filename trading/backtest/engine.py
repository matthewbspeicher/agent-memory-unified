"""Importable backtest engine for agent draft validation.

Refactored from scripts/backtest_system.py into a library module that
can be called from FastAPI endpoints via run_in_executor.

Usage:
    from backtest.engine import run_backtest

    results = run_backtest(
        symbols=["BTC", "ETH"],
        days=90,
        regime_weights={"trending": {"technical": 0.4, ...}},
    )
"""

from __future__ import annotations

import random
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta


@dataclass
class BacktestResult:
    sharpe_ratio: float
    win_rate: float
    max_drawdown: float
    total_trades: int
    total_return_pct: float
    initial_capital: float
    final_value: float
    volatility: float
    equity_curve: list[dict]
    status: str = "real"


_BASE_PRICES: dict[str, float] = {
    "BTC": 70000,
    "ETH": 2000,
    "SOL": 80,
    "ADA": 0.5,
    "DOGE": 0.15,
    "AAPL": 220,
    "MSFT": 450,
    "GOOGL": 180,
    "AMZN": 200,
    "NVDA": 130,
}

_DEFAULT_REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "trending": {"technical": 0.40, "sentiment": 0.20, "whale": 0.15, "momentum": 0.25},
    "ranging": {"technical": 0.30, "sentiment": 0.30, "whale": 0.25, "momentum": 0.15},
    "volatile": {"technical": 0.25, "sentiment": 0.25, "whale": 0.30, "momentum": 0.20},
}


def _generate_historical_data(symbol: str, days: int) -> list[dict]:
    price = _BASE_PRICES.get(symbol, 100.0)
    data = []
    start = datetime.now() - timedelta(days=days)

    for i in range(days):
        price *= 1 + random.gauss(0.001, 0.03)
        rsi = max(10, min(90, 50 + random.gauss(0, 15)))
        data.append({
            "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
            "price": price,
            "rsi": rsi,
            "volume": random.expovariate(1 / 1_000_000) * 1_000_000,
            "sentiment": max(0, min(100, 50 + random.gauss(0, 20))),
            "whale_flow": random.gauss(0, 500_000),
            "high": price * (1 + random.uniform(0, 0.02)),
            "low": price * (1 - random.uniform(0, 0.02)),
        })
    return data


def _detect_regime(data_slice: list[dict]) -> str:
    if len(data_slice) < 20:
        return "ranging"
    prices = [d["price"] for d in data_slice[-20:]]
    returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
    volatility = statistics.stdev(returns) if len(returns) > 1 else 0.02
    trend_strength = abs(returns[-1]) if returns else 0
    if volatility > 0.04:
        return "volatile"
    if trend_strength > 0.02:
        return "trending"
    return "ranging"


def _calculate_signal(
    data_point: dict, regime: str, weights: dict[str, dict[str, float]]
) -> tuple[str, float]:
    w = weights.get(regime, weights.get("ranging", _DEFAULT_REGIME_WEIGHTS["ranging"]))

    technical_score = -1 if data_point["rsi"] > 70 else (1 if data_point["rsi"] < 30 else 0)
    sentiment_score = (data_point["sentiment"] - 50) / 50
    whale_score = 1 if data_point["whale_flow"] > 0 else -1
    momentum_score = 0
    if "prev_price" in data_point:
        momentum_score = max(
            -1, min(1, (data_point["price"] - data_point["prev_price"]) / data_point["prev_price"] * 10)
        )

    composite = (
        technical_score * w.get("technical", 0.3)
        + sentiment_score * w.get("sentiment", 0.2)
        + whale_score * w.get("whale", 0.2)
        + momentum_score * w.get("momentum", 0.3)
    )
    confidence = min(abs(composite) * 100, 100)

    if composite > 0.2:
        return "BUY", confidence
    if composite < -0.2:
        return "SELL", confidence
    return "HOLD", confidence


def run_backtest(
    symbols: list[str] | None = None,
    days: int = 90,
    initial_capital: float = 100_000,
    regime_weights: dict[str, dict[str, float]] | None = None,
) -> dict:
    """Run a full backtest. Returns a dict matching the BacktestResult shape.

    This is a synchronous, CPU-bound function. Call from async code via
    ``asyncio.get_event_loop().run_in_executor(None, ...)``.
    """
    symbols = symbols or ["BTC", "ETH"]
    weights = regime_weights or _DEFAULT_REGIME_WEIGHTS

    capital = initial_capital
    positions: dict[str, float] = {}
    trades: list[dict] = []
    equity_curve: list[dict] = []

    historical = {s: _generate_historical_data(s, days) for s in symbols}

    for i in range(days):
        current_date = historical[symbols[0]][i]["date"]
        total_value = capital

        for symbol in symbols:
            dp = historical[symbol][i]
            if i > 0:
                dp["prev_price"] = historical[symbol][i - 1]["price"]

            regime = _detect_regime(historical[symbol][max(0, i - 20) : i + 1])
            action, confidence = _calculate_signal(dp, regime, weights)

            if confidence > 50:
                position_size = min(capital * 0.2, capital * (confidence / 100) * 0.3)

                if action == "BUY" and position_size > 100:
                    qty = position_size / dp["price"]
                    positions[symbol] = positions.get(symbol, 0) + qty
                    capital -= position_size
                    trades.append({
                        "timestamp": current_date,
                        "symbol": symbol,
                        "action": "BUY",
                        "price": dp["price"],
                        "quantity": qty,
                        "value_usd": position_size,
                    })
                elif action == "SELL" and positions.get(symbol, 0) > 0:
                    qty = positions[symbol]
                    value = qty * dp["price"]
                    capital += value
                    positions[symbol] = 0
                    trades.append({
                        "timestamp": current_date,
                        "symbol": symbol,
                        "action": "SELL",
                        "price": dp["price"],
                        "quantity": qty,
                        "value_usd": value,
                    })

            if symbol in positions:
                total_value += positions[symbol] * dp["price"]

        equity_curve.append({"timestamp": current_date, "equity": round(float(total_value), 2)})

    # Metrics
    final_value = equity_curve[-1]["equity"] if equity_curve else initial_capital
    total_return = (final_value - initial_capital) / initial_capital * 100

    daily_returns = []
    for j in range(1, len(equity_curve)):
        prev = equity_curve[j - 1]["equity"]
        curr = equity_curve[j]["equity"]
        daily_returns.append((curr - prev) / prev if prev else 0)

    # Sharpe
    sharpe = 0.0
    if len(daily_returns) >= 2:
        avg_r = statistics.mean(daily_returns)
        std_r = statistics.stdev(daily_returns)
        if std_r > 0:
            sharpe = (avg_r * 365 - 0.02) / (std_r * 365**0.5)

    # Max drawdown
    peak = equity_curve[0]["equity"] if equity_curve else initial_capital
    max_dd = 0.0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = (peak - pt["equity"]) / peak
        if dd > max_dd:
            max_dd = dd

    win_rate = (
        sum(1 for t in trades if t["action"] == "SELL") / max(len(trades), 1)
    )

    return {
        "sharpe_ratio": round(sharpe, 2),
        "win_rate": round(win_rate, 2),
        "max_drawdown": round(-max_dd, 4),
        "total_trades": len(trades),
        "total_return_pct": round(total_return, 2),
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "volatility": round(statistics.stdev(daily_returns) * 100, 2) if len(daily_returns) > 1 else 0,
        "equity_curve": equity_curve,
        "status": "real",
    }
