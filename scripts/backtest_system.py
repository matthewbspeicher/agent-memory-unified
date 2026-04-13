#!/usr/bin/env python3
import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass
import statistics


@dataclass
class Trade:
    timestamp: str
    symbol: str
    action: str
    price: float
    quantity: float
    value_usd: float
    signal_confidence: float
    regime: str


class BacktestEngine:
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions: Dict[str, float] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []
        self.metrics: Dict = {}

        self.regime_weights = {
            "trending": {
                "technical": 0.40,
                "sentiment": 0.20,
                "whale": 0.15,
                "momentum": 0.25,
            },
            "ranging": {
                "technical": 0.30,
                "sentiment": 0.30,
                "whale": 0.25,
                "momentum": 0.15,
            },
            "volatile": {
                "technical": 0.25,
                "sentiment": 0.25,
                "whale": 0.30,
                "momentum": 0.20,
            },
        }

    def generate_historical_data(self, symbol: str, days: int = 365) -> List[Dict]:
        base_price = {"BTC": 70000, "ETH": 2000, "SOL": 80, "ADA": 0.5, "DOGE": 0.15}
        price = base_price.get(symbol, 100)

        data = []
        current_date = datetime.now() - timedelta(days=days)

        for i in range(days):
            daily_return = random.gauss(0.001, 0.03)
            price *= 1 + daily_return

            rsi = 50 + random.gauss(0, 15)
            rsi = max(10, min(90, rsi))

            volume = random.expovariate(1 / 1000000) * 1000000

            sentiment = 50 + random.gauss(0, 20)
            sentiment = max(0, min(100, sentiment))

            whale_flow = random.gauss(0, 500000)

            data.append(
                {
                    "date": (current_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                    "price": price,
                    "rsi": rsi,
                    "volume": volume,
                    "sentiment": sentiment,
                    "whale_flow": whale_flow,
                    "high": price * (1 + random.uniform(0, 0.02)),
                    "low": price * (1 - random.uniform(0, 0.02)),
                }
            )

        return data

    def detect_regime(self, data_slice: List[Dict]) -> str:
        if len(data_slice) < 20:
            return "ranging"

        prices = [d["price"] for d in data_slice[-20:]]
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
        ]

        volatility = statistics.stdev(returns) if len(returns) > 1 else 0.02
        trend_strength = abs(returns[-1]) if returns else 0

        if volatility > 0.04:
            return "volatile"
        elif trend_strength > 0.02:
            return "trending"
        else:
            return "ranging"

    def calculate_signal(self, data_point: Dict, regime: str) -> Tuple[str, float]:
        weights = self.regime_weights[regime]

        technical_score = 0
        if data_point["rsi"] > 70:
            technical_score = -1
        elif data_point["rsi"] < 30:
            technical_score = 1

        sentiment_score = (data_point["sentiment"] - 50) / 50

        whale_score = 1 if data_point["whale_flow"] > 0 else -1

        momentum_score = 0
        if "prev_price" in data_point:
            momentum_score = (
                data_point["price"] - data_point["prev_price"]
            ) / data_point["prev_price"]
            momentum_score = max(-1, min(1, momentum_score * 10))

        composite = (
            technical_score * weights["technical"]
            + sentiment_score * weights["sentiment"]
            + whale_score * weights["whale"]
            + momentum_score * weights["momentum"]
        )

        confidence = min(abs(composite) * 100, 100)

        if composite > 0.2:
            return "BUY", confidence
        elif composite < -0.2:
            return "SELL", confidence
        else:
            return "HOLD", confidence

    def execute_trade(
        self,
        symbol: str,
        action: str,
        price: float,
        confidence: float,
        regime: str,
        date: str,
    ):
        position_size = min(self.capital * 0.2, self.capital * (confidence / 100) * 0.3)

        if action == "BUY" and position_size > 100:
            quantity = position_size / price
            self.positions[symbol] = self.positions.get(symbol, 0) + quantity
            self.capital -= position_size

            self.trades.append(
                Trade(
                    timestamp=date,
                    symbol=symbol,
                    action=action,
                    price=price,
                    quantity=quantity,
                    value_usd=position_size,
                    signal_confidence=confidence,
                    regime=regime,
                )
            )

        elif (
            action == "SELL" and symbol in self.positions and self.positions[symbol] > 0
        ):
            quantity = self.positions[symbol]
            value = quantity * price
            self.capital += value
            self.positions[symbol] = 0

            self.trades.append(
                Trade(
                    timestamp=date,
                    symbol=symbol,
                    action=action,
                    price=price,
                    quantity=quantity,
                    value_usd=value,
                    signal_confidence=confidence,
                    regime=regime,
                )
            )

    def run_backtest(self, symbols: List[str], days: int = 365) -> Dict:
        print(f"🔄 Running backtest for {len(symbols)} symbols over {days} days...")

        historical_data = {
            symbol: self.generate_historical_data(symbol, days) for symbol in symbols
        }

        for i in range(days):
            current_date = historical_data[symbols[0]][i]["date"]
            total_value = self.capital

            for symbol in symbols:
                data_point = historical_data[symbol][i]
                if i > 0:
                    data_point["prev_price"] = historical_data[symbol][i - 1]["price"]

                data_slice = historical_data[symbol][max(0, i - 20) : i + 1]
                regime = self.detect_regime(data_slice)

                action, confidence = self.calculate_signal(data_point, regime)

                if confidence > 50:
                    self.execute_trade(
                        symbol,
                        action,
                        data_point["price"],
                        confidence,
                        regime,
                        current_date,
                    )

                if symbol in self.positions:
                    total_value += self.positions[symbol] * data_point["price"]

            self.equity_curve.append(
                {
                    "date": current_date,
                    "total_value": total_value,
                    "capital": self.capital,
                    "positions": dict(self.positions),
                }
            )

        self._calculate_metrics()
        return self.metrics

    def _calculate_metrics(self):
        if not self.equity_curve:
            return

        final_value = self.equity_curve[-1]["total_value"]
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100

        daily_returns = []
        for i in range(1, len(self.equity_curve)):
            prev = self.equity_curve[i - 1]["total_value"]
            curr = self.equity_curve[i]["total_value"]
            daily_returns.append((curr - prev) / prev)

        winning_trades = [
            t for t in self.trades if t.action == "SELL" and t.value_usd > 0
        ]
        losing_trades = [
            t for t in self.trades if t.action == "SELL" and t.value_usd < 0
        ]

        self.metrics = {
            "initial_capital": self.initial_capital,
            "final_value": final_value,
            "total_return_pct": total_return,
            "total_trades": len(self.trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": len(winning_trades) / max(len(self.trades), 1) * 100,
            "max_drawdown": self._calculate_max_drawdown(),
            "sharpe_ratio": self._calculate_sharpe_ratio(daily_returns),
            "volatility": statistics.stdev(daily_returns) * 100
            if len(daily_returns) > 1
            else 0,
            "avg_trade_return": statistics.mean([t.value_usd for t in self.trades])
            if self.trades
            else 0,
        }

    def _calculate_max_drawdown(self) -> float:
        peak = self.equity_curve[0]["total_value"]
        max_dd = 0

        for point in self.equity_curve:
            value = point["total_value"]
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            if dd > max_dd:
                max_dd = dd

        return max_dd

    def _calculate_sharpe_ratio(
        self, returns: List[float], risk_free_rate: float = 0.02
    ) -> float:
        if not returns or len(returns) < 2:
            return 0

        avg_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)

        if std_return == 0:
            return 0

        annualized_return = avg_return * 365
        annualized_std = std_return * (365**0.5)

        return (annualized_return - risk_free_rate) / annualized_std

    def optimize_weights(self, symbols: List[str], weight_ranges: Dict) -> Dict:
        print("🎯 Optimizing signal weights...")

        best_sharpe = -999
        best_weights = None

        technical_range = weight_ranges.get("technical", [0.2, 0.3, 0.4, 0.5])
        sentiment_range = weight_ranges.get("sentiment", [0.1, 0.2, 0.3])
        whale_range = weight_ranges.get("whale", [0.1, 0.15, 0.2, 0.25])
        momentum_range = weight_ranges.get("momentum", [0.1, 0.15, 0.2, 0.25])

        for tech in technical_range:
            for sent in sentiment_range:
                for whale in whale_range:
                    for mom in momentum_range:
                        if abs(tech + sent + whale + mom - 1.0) > 0.01:
                            continue

                        self.regime_weights["trending"] = {
                            "technical": tech,
                            "sentiment": sent,
                            "whale": whale,
                            "momentum": mom,
                        }

                        self.reset()
                        self.run_backtest(symbols, days=180)

                        if self.metrics.get("sharpe_ratio", 0) > best_sharpe:
                            best_sharpe = self.metrics["sharpe_ratio"]
                            best_weights = {
                                "technical": tech,
                                "sentiment": sent,
                                "whale": whale,
                                "momentum": mom,
                            }

        print(f"✅ Best weights found: {best_weights}")
        print(f"   Sharpe Ratio: {best_sharpe:.3f}")

        return best_weights

    def reset(self):
        self.capital = self.initial_capital
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        self.metrics = {}

    def print_results(self):
        print("\n" + "=" * 70)
        print("📊 BACKTEST RESULTS")
        print("=" * 70)

        print(f"\n💰 Performance:")
        print(f"  Initial Capital: ${self.initial_capital:,.2f}")
        print(f"  Final Value: ${self.metrics.get('final_value', 0):,.2f}")
        print(f"  Total Return: {self.metrics.get('total_return_pct', 0):.2f}%")

        print(f"\n📈 Risk Metrics:")
        print(f"  Sharpe Ratio: {self.metrics.get('sharpe_ratio', 0):.3f}")
        print(f"  Max Drawdown: {self.metrics.get('max_drawdown', 0):.2f}%")
        print(f"  Volatility: {self.metrics.get('volatility', 0):.2f}%")

        print(f"\n🎯 Trade Statistics:")
        print(f"  Total Trades: {self.metrics.get('total_trades', 0)}")
        print(f"  Win Rate: {self.metrics.get('win_rate', 0):.1f}%")
        print(f"  Avg Trade Value: ${self.metrics.get('avg_trade_return', 0):,.2f}")

        print("\n" + "=" * 70)


def run_backtest_demo():
    engine = BacktestEngine(initial_capital=100000)

    symbols = ["BTC", "ETH", "SOL"]
    engine.run_backtest(symbols, days=365)
    engine.print_results()

    print("\n🎯 Weight Optimization Test:")
    optimal_weights = engine.optimize_weights(
        symbols,
        weight_ranges={
            "technical": [0.3, 0.4, 0.5],
            "sentiment": [0.15, 0.2, 0.25],
            "whale": [0.1, 0.15, 0.2],
            "momentum": [0.15, 0.2, 0.25],
        },
    )

    results = {
        "timestamp": datetime.now().isoformat(),
        "symbols_tested": symbols,
        "metrics": engine.metrics,
        "optimal_weights": optimal_weights,
    }

    with open("/opt/agent-memory-unified/data/backtest_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n✅ Results saved to data/backtest_results.json")
    return engine


if __name__ == "__main__":
    run_backtest_demo()
