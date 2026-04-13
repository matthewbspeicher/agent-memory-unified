#!/usr/bin/env python3
"""Integrated Signal - Combines sentiment + technicals + whale data"""

import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class SignalStrength(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class SignalComponent:
    name: str
    score: float
    weight: float
    interpretation: str


@dataclass
class IntegratedSignal:
    symbol: str
    composite_score: float
    signal_strength: SignalStrength
    confidence: float
    components: List[SignalComponent]
    timestamp: datetime
    recommendation: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class IntegratedSignalGenerator:
    WEIGHTS = {
        "sentiment": 0.25,
        "technical": 0.35,
        "whale": 0.20,
        "momentum": 0.20,
    }

    def __init__(self):
        self.signals = {}

    def calculate_technical_score(self, tech_data: Dict) -> SignalComponent:
        score = 0
        reasons = []

        rsi = tech_data.get("rsi", 50)
        if rsi > 70:
            score -= 30
            reasons.append(f"RSI overbought ({rsi:.0f})")
        elif rsi < 30:
            score += 30
            reasons.append(f"RSI oversold ({rsi:.0f})")
        elif rsi > 60:
            score -= 10
            reasons.append(f"RSI elevated ({rsi:.0f})")
        elif rsi < 40:
            score += 10
            reasons.append(f"RSI depressed ({rsi:.0f})")

        if tech_data.get("golden_cross"):
            score += 25
            reasons.append("Golden Cross detected")
        elif tech_data.get("death_cross"):
            score -= 25
            reasons.append("Death Cross detected")

        bb_position = tech_data.get("bb_position", "middle")
        if bb_position == "upper":
            score -= 15
            reasons.append("At upper Bollinger Band")
        elif bb_position == "lower":
            score += 15
            reasons.append("At lower Bollinger Band")

        macd_signal = tech_data.get("macd_signal", "neutral")
        if macd_signal == "bullish":
            score += 15
            reasons.append("MACD bullish crossover")
        elif macd_signal == "bearish":
            score -= 15
            reasons.append("MACD bearish crossover")

        interpretation = "; ".join(reasons) if reasons else "Neutral technicals"

        return SignalComponent(
            name="Technical Analysis",
            score=max(-100, min(100, score)),
            weight=self.WEIGHTS["technical"],
            interpretation=interpretation,
        )

    def calculate_sentiment_score(self, sentiment_data: Dict) -> SignalComponent:
        fear_greed = sentiment_data.get("fear_greed_index", 50)

        if fear_greed < 20:
            score = 80
            interpretation = f"Extreme Fear ({fear_greed}) - Strong contrarian BUY"
        elif fear_greed < 35:
            score = 50
            interpretation = f"Fear ({fear_greed}) - Contrarian BUY"
        elif fear_greed < 45:
            score = 20
            interpretation = f"Mild Fear ({fear_greed}) - Slight BUY bias"
        elif fear_greed > 80:
            score = -80
            interpretation = f"Extreme Greed ({fear_greed}) - Strong contrarian SELL"
        elif fear_greed > 65:
            score = -50
            interpretation = f"Greed ({fear_greed}) - Contrarian SELL"
        elif fear_greed > 55:
            score = -20
            interpretation = f"Mild Greed ({fear_greed}) - Slight SELL bias"
        else:
            score = 0
            interpretation = f"Neutral ({fear_greed}) - No sentiment edge"

        return SignalComponent(
            name="Market Sentiment",
            score=score,
            weight=self.WEIGHTS["sentiment"],
            interpretation=interpretation,
        )

    def calculate_whale_score(self, whale_data: Dict) -> SignalComponent:
        net_flow = whale_data.get("net_flow_usd", 0)

        if net_flow > 50_000_000:
            score = 60
            interpretation = f"Strong accumulation (${net_flow / 1e6:.0f}M net outflow)"
        elif net_flow > 10_000_000:
            score = 30
            interpretation = f"Mild accumulation (${net_flow / 1e6:.0f}M net outflow)"
        elif net_flow < -50_000_000:
            score = -60
            interpretation = (
                f"Strong distribution (${abs(net_flow) / 1e6:.0f}M net inflow)"
            )
        elif net_flow < -10_000_000:
            score = -30
            interpretation = (
                f"Mild distribution (${abs(net_flow) / 1e6:.0f}M net inflow)"
            )
        else:
            score = 0
            interpretation = "Balanced whale activity"

        return SignalComponent(
            name="Whale Activity",
            score=score,
            weight=self.WEIGHTS["whale"],
            interpretation=interpretation,
        )

    def calculate_momentum_score(self, price_data: Dict) -> SignalComponent:
        change_24h = price_data.get("change_24h", 0)
        change_7d = price_data.get("change_7d", 0)
        volume_ratio = price_data.get("volume_ratio", 1.0)

        score = 0
        reasons = []

        if change_24h > 10:
            score += 30
            reasons.append(f"Strong 24h gain (+{change_24h:.1f}%)")
        elif change_24h > 5:
            score += 15
            reasons.append(f"Moderate 24h gain (+{change_24h:.1f}%)")
        elif change_24h < -10:
            score -= 30
            reasons.append(f"Strong 24h loss ({change_24h:.1f}%)")
        elif change_24h < -5:
            score -= 15
            reasons.append(f"Moderate 24h loss ({change_24h:.1f}%)")

        if change_7d > 20:
            score += 20
            reasons.append(f"Strong weekly gain (+{change_7d:.1f}%)")
        elif change_7d < -20:
            score -= 20
            reasons.append(f"Strong weekly loss ({change_7d:.1f}%)")

        if volume_ratio > 2:
            score += 10
            reasons.append(f"High volume ({volume_ratio:.1f}x avg)")
        elif volume_ratio < 0.5:
            score -= 10
            reasons.append(f"Low volume ({volume_ratio:.1f}x avg)")

        interpretation = "; ".join(reasons) if reasons else "Neutral momentum"

        return SignalComponent(
            name="Price Momentum",
            score=max(-100, min(100, score)),
            weight=self.WEIGHTS["momentum"],
            interpretation=interpretation,
        )

    def generate_signal(
        self,
        symbol: str,
        current_price: float,
        technical_data: Dict,
        sentiment_data: Dict,
        whale_data: Dict,
        price_data: Dict,
    ) -> IntegratedSignal:
        components = [
            self.calculate_technical_score(technical_data),
            self.calculate_sentiment_score(sentiment_data),
            self.calculate_whale_score(whale_data),
            self.calculate_momentum_score(price_data),
        ]

        composite_score = sum(c.score * c.weight for c in components)

        total_weight = sum(c.weight for c in components)
        confidence = min(100, abs(composite_score) * 1.5)

        if composite_score >= 60:
            strength = SignalStrength.STRONG_BUY
            recommendation = "Strong buy signal - multiple factors aligned bullish"
        elif composite_score >= 25:
            strength = SignalStrength.BUY
            recommendation = "Buy signal - net bullish factors"
        elif composite_score <= -60:
            strength = SignalStrength.STRONG_SELL
            recommendation = "Strong sell signal - multiple factors aligned bearish"
        elif composite_score <= -25:
            strength = SignalStrength.SELL
            recommendation = "Sell signal - net bearish factors"
        else:
            strength = SignalStrength.NEUTRAL
            recommendation = "Neutral - conflicting signals, wait for clarity"

        if strength in [SignalStrength.BUY, SignalStrength.STRONG_BUY]:
            stop_loss = current_price * 0.92
            take_profit = current_price * 1.15
        elif strength in [SignalStrength.SELL, SignalStrength.STRONG_SELL]:
            stop_loss = current_price * 1.08
            take_profit = current_price * 0.85
        else:
            stop_loss = None
            take_profit = None

        return IntegratedSignal(
            symbol=symbol,
            composite_score=composite_score,
            signal_strength=strength,
            confidence=confidence,
            components=components,
            timestamp=datetime.now(),
            recommendation=recommendation,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )


def format_signal_report(signal: IntegratedSignal) -> str:
    strength_emoji = {
        SignalStrength.STRONG_BUY: "🟢🟢",
        SignalStrength.BUY: "🟢",
        SignalStrength.NEUTRAL: "⚪",
        SignalStrength.SELL: "🔴",
        SignalStrength.STRONG_SELL: "🔴🔴",
    }

    report = f"""
{"=" * 70}
📊 INTEGRATED TRADING SIGNAL
{"=" * 70}

Symbol: {signal.symbol}
Timestamp: {signal.timestamp.strftime("%Y-%m-%d %H:%M:%S")}

🎯 SIGNAL: {strength_emoji.get(signal.signal_strength, "")} {signal.signal_strength.value}
   Composite Score: {signal.composite_score:+.1f}/100
   Confidence: {signal.confidence:.0f}%

💡 RECOMMENDATION:
   {signal.recommendation}

📈 TRADE SETUP:
   Entry: ${signal.entry_price:,.2f}"""

    if signal.stop_loss:
        report += f"""
   Stop Loss: ${signal.stop_loss:,.2f} ({((signal.stop_loss / signal.entry_price) - 1) * 100:+.1f}%)
   Take Profit: ${signal.take_profit:,.2f} ({((signal.take_profit / signal.entry_price) - 1) * 100:+.1f}%)"""

    report += f"""

{"=" * 70}
📋 SIGNAL COMPONENTS
{"=" * 70}
"""

    for component in signal.components:
        score_bar = "█" * int(abs(component.score) / 10)
        direction = "+" if component.score >= 0 else "-"
        report += f"""
{component.name} (Weight: {component.weight * 100:.0f}%)
   Score: {component.score:+.1f} {direction}{score_bar}
   {component.interpretation}
"""

    report += f"""
{"=" * 70}
⚖️ SIGNAL ANALYSIS
{"=" * 70}

Bullish Factors:
"""
    bullish = [c for c in signal.components if c.score > 10]
    bearish = [c for c in signal.components if c.score < -10]
    neutral = [c for c in signal.components if -10 <= c.score <= 10]

    if bullish:
        for c in bullish:
            report += f"   ✅ {c.name}: {c.score:+.1f}\n"
    else:
        report += "   (none)\n"

    report += "\nBearish Factors:\n"
    if bearish:
        for c in bearish:
            report += f"   ❌ {c.name}: {c.score:+.1f}\n"
    else:
        report += "   (none)\n"

    report += f"""
Neutral Factors:
"""
    if neutral:
        for c in neutral:
            report += f"   ⚪ {c.name}: {c.score:+.1f}\n"
    else:
        report += "   (none)\n"

    return report


def main():
    print("=" * 70)
    print("📊 INTEGRATED SIGNAL GENERATOR")
    print("=" * 70)
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    generator = IntegratedSignalGenerator()

    test_cases = [
        {
            "symbol": "BTC",
            "current_price": 73123.0,
            "technical": {
                "rsi": 78,
                "death_cross": True,
                "bb_position": "upper",
                "macd_signal": "bearish",
            },
            "sentiment": {"fear_greed_index": 16},
            "whale": {"net_flow_usd": -25_000_000},
            "price_data": {"change_24h": -2.5, "change_7d": 5.2, "volume_ratio": 1.2},
        },
        {
            "symbol": "ETH",
            "current_price": 2248.0,
            "technical": {
                "rsi": 73,
                "golden_cross": True,
                "bb_position": "upper",
                "macd_signal": "neutral",
            },
            "sentiment": {"fear_greed_index": 16},
            "whale": {"net_flow_usd": -15_000_000},
            "price_data": {"change_24h": -1.8, "change_7d": 3.5, "volume_ratio": 1.1},
        },
        {
            "symbol": "SOL",
            "current_price": 84.87,
            "technical": {
                "rsi": 54,
                "death_cross": True,
                "bb_position": "middle",
                "macd_signal": "neutral",
            },
            "sentiment": {"fear_greed_index": 16},
            "whale": {"net_flow_usd": 5_000_000},
            "price_data": {"change_24h": -3.2, "change_7d": -8.5, "volume_ratio": 0.9},
        },
    ]

    all_signals = []

    for test in test_cases:
        signal = generator.generate_signal(
            symbol=test["symbol"],
            current_price=test["current_price"],
            technical_data=test["technical"],
            sentiment_data=test["sentiment"],
            whale_data=test["whale"],
            price_data=test["price_data"],
        )
        all_signals.append(signal)
        print(format_signal_report(signal))

    print("\n" + "=" * 70)
    print("📊 SIGNAL SUMMARY")
    print("=" * 70)
    print(f"\n{'Symbol':<10} {'Signal':<15} {'Score':<10} {'Confidence':<12}")
    print("-" * 50)
    for signal in all_signals:
        print(
            f"{signal.symbol:<10} {signal.signal_strength.value:<15} {signal.composite_score:>+7.1f} {signal.confidence:>8.0f}%"
        )

    output_file = "/opt/agent-memory-unified/data/integrated_signals.json"
    with open(output_file, "w") as f:
        json.dump(
            [
                {
                    "symbol": s.symbol,
                    "signal": s.signal_strength.value,
                    "composite_score": s.composite_score,
                    "confidence": s.confidence,
                    "recommendation": s.recommendation,
                    "entry_price": s.entry_price,
                    "stop_loss": s.stop_loss,
                    "take_profit": s.take_profit,
                    "components": [
                        {
                            "name": c.name,
                            "score": c.score,
                            "weight": c.weight,
                            "interpretation": c.interpretation,
                        }
                        for c in s.components
                    ],
                    "timestamp": s.timestamp.isoformat(),
                }
                for s in all_signals
            ],
            f,
            indent=2,
        )
    print(f"\n💾 Results saved to: {output_file}")


if __name__ == "__main__":
    main()
