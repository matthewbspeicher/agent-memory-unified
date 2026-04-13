#!/usr/bin/env python3
"""
Technical Signal Generator - RSI, MACD, Moving Averages
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional
import aiohttp
import numpy as np


class TechnicalAnalyzer:
    """Generate trading signals using technical indicators"""

    def __init__(self):
        self.price_history = {}

    async def get_price_history(self, symbol: str, days: int = 100) -> List[float]:
        """Fetch historical prices from CoinGecko"""
        url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart"
        params = {"vs_currency": "usd", "days": days, "interval": "daily"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    prices = [p[1] for p in data["prices"]]
                    self.price_history[symbol] = prices
                    return prices

        return []

    def calculate_sma(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return None
        return np.mean(prices[-period:])

    def calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = prices[0]

        for price in prices[1:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return None

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_macd(
        self,
        prices: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> Dict:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        if len(prices) < slow_period:
            return {"macd": None, "signal": None, "histogram": None}

        # Calculate EMAs
        fast_ema = self.calculate_ema(prices, fast_period)
        slow_ema = self.calculate_ema(prices, slow_period)

        if fast_ema is None or slow_ema is None:
            return {"macd": None, "signal": None, "histogram": None}

        macd_line = fast_ema - slow_ema

        # For signal line, we'd need MACD history - simplified here
        signal_line = macd_line * 0.9  # Simplified
        histogram = macd_line - signal_line

        return {"macd": macd_line, "signal": signal_line, "histogram": histogram}

    def calculate_bollinger_bands(
        self, prices: List[float], period: int = 20, std_dev: float = 2.0
    ) -> Dict:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return {"upper": None, "middle": None, "lower": None}

        recent_prices = prices[-period:]
        middle = np.mean(recent_prices)
        std = np.std(recent_prices)

        return {
            "upper": middle + (std * std_dev),
            "middle": middle,
            "lower": middle - (std * std_dev),
            "percent_b": (prices[-1] - (middle - std * std_dev)) / (2 * std * std_dev)
            if std > 0
            else 0.5,
        }

    def generate_signal(self, prices: List[float], symbol: str) -> Dict:
        """Generate comprehensive trading signal"""
        if len(prices) < 50:
            return {"error": "Insufficient price history"}

        current_price = prices[-1]

        # Calculate indicators
        rsi = self.calculate_rsi(prices)
        macd = self.calculate_macd(prices)
        bollinger = self.calculate_bollinger_bands(prices)

        sma_20 = self.calculate_sma(prices, 20)
        sma_50 = self.calculate_sma(prices, 50)
        ema_12 = self.calculate_ema(prices, 12)
        ema_26 = self.calculate_ema(prices, 26)

        # Signal scoring
        signals = []
        score = 0

        # RSI signals
        if rsi is not None:
            if rsi < 30:
                signals.append(
                    {
                        "indicator": "RSI",
                        "signal": "OVERSOLD",
                        "value": rsi,
                        "weight": 2,
                    }
                )
                score += 2
            elif rsi > 70:
                signals.append(
                    {
                        "indicator": "RSI",
                        "signal": "OVERBOUGHT",
                        "value": rsi,
                        "weight": -2,
                    }
                )
                score -= 2
            else:
                signals.append(
                    {"indicator": "RSI", "signal": "NEUTRAL", "value": rsi, "weight": 0}
                )

        # Moving average crossover
        if sma_20 and sma_50:
            if sma_20 > sma_50:
                signals.append(
                    {
                        "indicator": "MA_CROSS",
                        "signal": "GOLDEN_CROSS",
                        "value": sma_20 / sma_50,
                        "weight": 2,
                    }
                )
                score += 2
            else:
                signals.append(
                    {
                        "indicator": "MA_CROSS",
                        "signal": "DEATH_CROSS",
                        "value": sma_20 / sma_50,
                        "weight": -2,
                    }
                )
                score -= 2

        # Price vs moving averages
        if sma_20:
            if current_price > sma_20:
                signals.append(
                    {
                        "indicator": "PRICE_VS_SMA20",
                        "signal": "ABOVE",
                        "value": current_price / sma_20,
                        "weight": 1,
                    }
                )
                score += 1
            else:
                signals.append(
                    {
                        "indicator": "PRICE_VS_SMA20",
                        "signal": "BELOW",
                        "value": current_price / sma_20,
                        "weight": -1,
                    }
                )
                score -= 1

        # MACD signals
        if macd["histogram"] is not None:
            if macd["histogram"] > 0:
                signals.append(
                    {
                        "indicator": "MACD",
                        "signal": "BULLISH",
                        "value": macd["histogram"],
                        "weight": 1,
                    }
                )
                score += 1
            else:
                signals.append(
                    {
                        "indicator": "MACD",
                        "signal": "BEARISH",
                        "value": macd["histogram"],
                        "weight": -1,
                    }
                )
                score -= 1

        # Bollinger Bands signals
        if bollinger["percent_b"] is not None:
            if bollinger["percent_b"] < 0.2:
                signals.append(
                    {
                        "indicator": "BOLLINGER",
                        "signal": "LOWER_BAND",
                        "value": bollinger["percent_b"],
                        "weight": 1,
                    }
                )
                score += 1
            elif bollinger["percent_b"] > 0.8:
                signals.append(
                    {
                        "indicator": "BOLLINGER",
                        "signal": "UPPER_BAND",
                        "value": bollinger["percent_b"],
                        "weight": -1,
                    }
                )
                score -= 1

        # Determine overall signal
        if score >= 3:
            direction = "STRONG_BUY"
            confidence = min(0.9, 0.5 + (score * 0.1))
        elif score >= 1:
            direction = "BUY"
            confidence = 0.6
        elif score <= -3:
            direction = "STRONG_SELL"
            confidence = min(0.9, 0.5 + (abs(score) * 0.1))
        elif score <= -1:
            direction = "SELL"
            confidence = 0.6
        else:
            direction = "HOLD"
            confidence = 0.5

        # Calculate entry levels
        stop_loss = current_price * 0.95  # 5% below
        take_profit = current_price * 1.15  # 15% above

        return {
            "symbol": symbol,
            "current_price": current_price,
            "direction": direction,
            "confidence": confidence,
            "score": score,
            "signals": signals,
            "indicators": {
                "rsi": rsi,
                "macd": macd,
                "bollinger": bollinger,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "ema_12": ema_12,
                "ema_26": ema_26,
            },
            "levels": {
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward": (take_profit - current_price)
                / (current_price - stop_loss),
            },
            "timestamp": datetime.now().isoformat(),
        }

    def generate_report(self, signal: Dict) -> str:
        """Generate formatted signal report"""
        lines = [
            "=" * 70,
            f"📊 TECHNICAL ANALYSIS - {signal['symbol'].upper()}",
            f"Generated: {signal['timestamp']}",
            "=" * 70,
            "",
            f"💰 Current Price: ${signal['current_price']:,.2f}",
            f"🎯 Signal: {signal['direction']}",
            f"📊 Confidence: {signal['confidence']:.0%}",
            f"📈 Score: {signal['score']:+d}",
            "",
            "📉 INDICATORS",
            "-" * 70,
        ]

        indicators = signal["indicators"]

        # RSI
        if indicators["rsi"] is not None:
            rsi = indicators["rsi"]
            rsi_status = (
                "Oversold" if rsi < 30 else "Overbought" if rsi > 70 else "Neutral"
            )
            lines.append(f"  RSI (14): {rsi:.1f} - {rsi_status}")

        # Moving Averages
        if indicators["sma_20"] and indicators["sma_50"]:
            lines.append(f"  SMA 20: ${indicators['sma_20']:,.2f}")
            lines.append(f"  SMA 50: ${indicators['sma_50']:,.2f}")
            cross = (
                "Golden Cross"
                if indicators["sma_20"] > indicators["sma_50"]
                else "Death Cross"
            )
            lines.append(f"  MA Cross: {cross}")

        # MACD
        if indicators["macd"]["histogram"] is not None:
            macd_status = (
                "Bullish" if indicators["macd"]["histogram"] > 0 else "Bearish"
            )
            lines.append(
                f"  MACD Histogram: {indicators['macd']['histogram']:.2f} - {macd_status}"
            )

        # Bollinger Bands
        if indicators["bollinger"]["upper"]:
            lines.append(f"  Bollinger Bands:")
            lines.append(f"    Upper: ${indicators['bollinger']['upper']:,.2f}")
            lines.append(f"    Middle: ${indicators['bollinger']['middle']:,.2f}")
            lines.append(f"    Lower: ${indicators['bollinger']['lower']:,.2f}")
            lines.append(f"    %B: {indicators['bollinger']['percent_b']:.2f}")

        lines.extend(
            [
                "",
                "🎯 TRADING LEVELS",
                "-" * 70,
                f"  Entry: ${signal['current_price']:,.2f}",
                f"  Stop Loss: ${signal['levels']['stop_loss']:,.2f} (-5%)",
                f"  Take Profit: ${signal['levels']['take_profit']:,.2f} (+15%)",
                f"  Risk/Reward: 1:{signal['levels']['risk_reward']:.1f}",
                "",
                "📋 SIGNAL DETAILS",
                "-" * 70,
            ]
        )

        for s in signal["signals"]:
            indicator = s["indicator"]
            sig = s["signal"]
            value = s["value"]
            weight = s["weight"]
            emoji = "🟢" if weight > 0 else "🔴" if weight < 0 else "⚪"
            lines.append(
                f"  {emoji} {indicator:15} {sig:15} Value: {value:.3f} Weight: {weight:+d}"
            )

        lines.extend(["", "=" * 70])
        return "\n".join(lines)


async def main():
    """Run technical analyzer"""
    print("🚀 Technical Signal Generator - Phase 1, Day 8-10")
    print("=" * 60)

    analyzer = TechnicalAnalyzer()

    # Analyze multiple assets
    assets = ["bitcoin", "ethereum", "solana"]

    for asset in assets:
        print(f"\n📡 Fetching {asset} price history...")
        prices = await analyzer.get_price_history(asset, days=100)

        if prices:
            signal = analyzer.generate_signal(prices, asset)
            report = analyzer.generate_report(signal)
            print(report)

            # Save signal
            with open(f"/opt/agent-memory-unified/data/signal_{asset}.json", "w") as f:
                json.dump(signal, f, indent=2, default=str)


if __name__ == "__main__":
    asyncio.run(main())
