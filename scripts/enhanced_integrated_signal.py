#!/usr/bin/env python3
"""
Enhanced Integrated Signal Generator
Tracks top 10 crypto assets with optimized signal weights
"""

import json
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import statistics

# Configuration
COINGECKO_API_KEY = "CG-oL81mP8oWpvHM1JMiXN5chEC"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Top 10 crypto assets by market cap
TOP_ASSETS = [
    {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin"},
    {"id": "ethereum", "symbol": "ETH", "name": "Ethereum"},
    {"id": "tether", "symbol": "USDT", "name": "Tether"},
    {"id": "binancecoin", "symbol": "BNB", "name": "BNB"},
    {"id": "solana", "symbol": "SOL", "name": "Solana"},
    {"id": "ripple", "symbol": "XRP", "name": "XRP"},
    {"id": "usd-coin", "symbol": "USDC", "name": "USD Coin"},
    {"id": "staked-ether", "symbol": "STETH", "name": "Lido Staked Ether"},
    {"id": "cardano", "symbol": "ADA", "name": "Cardano"},
    {"id": "dogecoin", "symbol": "DOGE", "name": "Dogecoin"},
]

# Optimized signal weights based on market conditions
OPTIMIZED_WEIGHTS = {
    "trending": {  # Strong trending market
        "technical": 0.40,
        "sentiment": 0.20,
        "whale": 0.15,
        "momentum": 0.25,
    },
    "ranging": {  # Sideways/ranging market
        "technical": 0.30,
        "sentiment": 0.30,
        "whale": 0.25,
        "momentum": 0.15,
    },
    "volatile": {  # High volatility market
        "technical": 0.25,
        "sentiment": 0.25,
        "whale": 0.30,
        "momentum": 0.20,
    },
}


class EnhancedIntegratedSignal:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"x-cg-demo-api-key": COINGECKO_API_KEY, "Accept": "application/json"}
        )
        self.cache = {}
        self.cache_ttl = 60  # 1 minute cache

    def get_market_data(self) -> List[Dict]:
        """Get current market data for all assets"""
        cache_key = "market_data"
        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            ids = ",".join([a["id"] for a in TOP_ASSETS])
            url = f"{COINGECKO_BASE}/coins/markets"
            params = {
                "vs_currency": "usd",
                "ids": ids,
                "order": "market_cap_desc",
                "sparkline": "true",
                "price_change_percentage": "1h,24h,7d,30d",
            }

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            self._update_cache(cache_key, data)
            return data

        except Exception as e:
            print(f"Error fetching market data: {e}")
            return []

    def calculate_technical_score(self, coin_data: Dict) -> Dict:
        """Calculate technical analysis score for an asset"""
        score = 50  # Neutral starting point
        signals = []

        # Price vs moving averages (using sparkline data)
        sparkline = coin_data.get("sparkline_in_7d", {}).get("price", [])
        if len(sparkline) >= 20:
            current_price = coin_data["current_price"]
            sma_20 = statistics.mean(sparkline[-20:])
            sma_7 = statistics.mean(sparkline[-7:])

            # Price vs SMA
            if current_price > sma_20:
                score += 10
                signals.append("Above SMA20")
            else:
                score -= 10
                signals.append("Below SMA20")

            # SMA crossover
            if sma_7 > sma_20:
                score += 5
                signals.append("SMA7 > SMA20")
            else:
                score -= 5
                signals.append("SMA7 < SMA20")

        # RSI approximation from price changes
        price_change_24h = coin_data.get("price_change_percentage_24h", 0)
        if price_change_24h > 5:
            score -= 15  # Overbought
            signals.append("Overbought (24h > 5%)")
        elif price_change_24h < -5:
            score += 15  # Oversold
            signals.append("Oversold (24h < -5%)")

        # Volatility consideration
        high_24h = coin_data.get("high_24h", 0)
        low_24h = coin_data.get("low_24h", 0)
        if high_24h > 0 and low_24h > 0:
            volatility = (high_24h - low_24h) / low_24h * 100
            if volatility > 10:
                score -= 5  # High volatility penalty
                signals.append(f"High volatility ({volatility:.1f}%)")

        return {
            "score": max(0, min(100, score)),
            "signals": signals,
            "interpretation": self._interpret_score(score),
        }

    def calculate_sentiment_score(self, coin_data: Dict) -> Dict:
        """Calculate sentiment score based on market data"""
        score = 50  # Neutral

        # Price momentum
        price_change_24h = coin_data.get("price_change_percentage_24h", 0)
        price_change_7d = coin_data.get("price_change_percentage_7d_in_currency", 0)

        # Weighted momentum
        momentum = (price_change_24h * 0.6) + (price_change_7d * 0.4)

        if momentum > 10:
            score += 25
        elif momentum > 5:
            score += 15
        elif momentum > 0:
            score += 5
        elif momentum > -5:
            score -= 5
        elif momentum > -10:
            score -= 15
        else:
            score -= 25

        # Volume analysis
        total_volume = coin_data.get("total_volume", 0)
        market_cap = coin_data.get("market_cap", 0)
        if market_cap > 0:
            volume_ratio = total_volume / market_cap
            if volume_ratio > 0.1:  # High volume
                score += 10
            elif volume_ratio < 0.01:  # Low volume
                score -= 5

        return {
            "score": max(0, min(100, score)),
            "momentum": momentum,
            "volume_ratio": volume_ratio if market_cap > 0 else 0,
        }

    def calculate_whale_score(self, coin_data: Dict) -> Dict:
        """Estimate whale activity based on volume and price action"""
        score = 50

        # Large volume relative to market cap suggests whale activity
        total_volume = coin_data.get("total_volume", 0)
        market_cap = coin_data.get("market_cap", 0)

        if market_cap > 0:
            volume_ratio = total_volume / market_cap

            # High volume with price increase = accumulation
            price_change_24h = coin_data.get("price_change_percentage_24h", 0)

            if volume_ratio > 0.15:  # Very high volume
                if price_change_24h > 0:
                    score += 30  # Accumulation
                else:
                    score -= 30  # Distribution
            elif volume_ratio > 0.08:  # High volume
                if price_change_24h > 0:
                    score += 15
                else:
                    score -= 15

        # Market cap rank as proxy for institutional interest
        market_cap_rank = coin_data.get("market_cap_rank") or 100
        if market_cap_rank <= 5:
            score += 10  # Top 5 have more institutional interest

        return {
            "score": max(0, min(100, score)),
            "volume_ratio": volume_ratio if market_cap > 0 else 0,
        }

    def calculate_momentum_score(self, coin_data: Dict) -> Dict:
        """Calculate momentum score from multiple timeframes"""
        score = 50

        # Multi-timeframe momentum
        change_1h = coin_data.get("price_change_percentage_1h_in_currency", 0) or 0
        change_24h = coin_data.get("price_change_percentage_24h", 0)
        change_7d = coin_data.get("price_change_percentage_7d_in_currency", 0) or 0
        change_30d = coin_data.get("price_change_percentage_30d_in_currency", 0) or 0

        # Weighted momentum score
        momentum = (
            change_1h * 0.1 + change_24h * 0.3 + change_7d * 0.3 + change_30d * 0.3
        )

        if momentum > 15:
            score += 40
        elif momentum > 8:
            score += 25
        elif momentum > 3:
            score += 10
        elif momentum > -3:
            score += 0
        elif momentum > -8:
            score -= 15
        elif momentum > -15:
            score -= 25
        else:
            score -= 40

        return {
            "score": max(0, min(100, score)),
            "momentum": momentum,
            "timeframes": {
                "1h": change_1h,
                "24h": change_24h,
                "7d": change_7d,
                "30d": change_30d,
            },
        }

    def determine_market_regime(self, all_assets: List[Dict]) -> str:
        """Determine current market regime for weight optimization"""
        if not all_assets:
            return "ranging"

        # Calculate average volatility and trend strength
        avg_volatility = 0
        avg_momentum = 0
        valid_count = 0

        for asset in all_assets:
            high = asset.get("high_24h", 0)
            low = asset.get("low_24h", 0)
            change = asset.get("price_change_percentage_24h", 0)

            if high > 0 and low > 0:
                volatility = (high - low) / low * 100
                avg_volatility += volatility
                avg_momentum += abs(change)
                valid_count += 1

        if valid_count > 0:
            avg_volatility /= valid_count
            avg_momentum /= valid_count

        # Determine regime
        if avg_volatility > 8:
            return "volatile"
        elif avg_momentum > 5:
            return "trending"
        else:
            return "ranging"

    def calculate_integrated_signal(self, coin_data: Dict, regime: str) -> Dict:
        """Calculate integrated signal with optimized weights"""
        # Get component scores
        technical = self.calculate_technical_score(coin_data)
        sentiment = self.calculate_sentiment_score(coin_data)
        whale = self.calculate_whale_score(coin_data)
        momentum = self.calculate_momentum_score(coin_data)

        # Get optimized weights for current regime
        weights = OPTIMIZED_WEIGHTS[regime]

        # Calculate weighted score
        weighted_score = (
            technical["score"] * weights["technical"]
            + sentiment["score"] * weights["sentiment"]
            + whale["score"] * weights["whale"]
            + momentum["score"] * weights["momentum"]
        )

        # Determine signal
        if weighted_score >= 70:
            signal = "STRONG BUY"
            action = "BUY"
            confidence = min(95, 60 + (weighted_score - 70) * 1.5)
        elif weighted_score >= 60:
            signal = "BUY"
            action = "BUY"
            confidence = 50 + (weighted_score - 60)
        elif weighted_score >= 45:
            signal = "NEUTRAL"
            action = "HOLD"
            confidence = 40
        elif weighted_score >= 35:
            signal = "SELL"
            action = "SELL"
            confidence = 50 + (45 - weighted_score)
        else:
            signal = "STRONG SELL"
            action = "SELL"
            confidence = min(95, 60 + (35 - weighted_score) * 1.5)

        return {
            "symbol": coin_data["symbol"].upper(),
            "name": coin_data["name"],
            "price": coin_data["current_price"],
            "market_cap_rank": coin_data.get("market_cap_rank", 0),
            "signal": signal,
            "action": action,
            "confidence": round(confidence, 1),
            "weighted_score": round(weighted_score, 1),
            "components": {
                "technical": technical,
                "sentiment": sentiment,
                "whale": whale,
                "momentum": momentum,
            },
            "weights_used": weights,
            "regime": regime,
        }

    def calculate_correlation_matrix(self, market_data: List[Dict]) -> Dict:
        """Calculate correlation between assets based on price changes"""
        correlations = {}

        # Use 24h and 7d changes for correlation
        for i, asset1 in enumerate(market_data):
            symbol1 = asset1["symbol"].upper()
            correlations[symbol1] = {}

            for j, asset2 in enumerate(market_data):
                symbol2 = asset2["symbol"].upper()

                if symbol1 == symbol2:
                    correlations[symbol1][symbol2] = 1.0
                else:
                    # Simple correlation based on price change similarity
                    change1_24h = asset1.get("price_change_percentage_24h", 0)
                    change2_24h = asset2.get("price_change_percentage_24h", 0)
                    change1_7d = (
                        asset1.get("price_change_percentage_7d_in_currency", 0) or 0
                    )
                    change2_7d = (
                        asset2.get("price_change_percentage_7d_in_currency", 0) or 0
                    )

                    # Calculate correlation coefficient (simplified)
                    changes1 = [change1_24h, change1_7d]
                    changes2 = [change2_24h, change2_7d]

                    mean1 = statistics.mean(changes1)
                    mean2 = statistics.mean(changes2)

                    numerator = sum(
                        (x - mean1) * (y - mean2) for x, y in zip(changes1, changes2)
                    )
                    denom1 = sum((x - mean1) ** 2 for x in changes1) ** 0.5
                    denom2 = sum((y - mean2) ** 2 for y in changes2) ** 0.5

                    if denom1 > 0 and denom2 > 0:
                        correlation = numerator / (denom1 * denom2)
                    else:
                        correlation = 0

                    correlations[symbol1][symbol2] = round(correlation, 2)

        return correlations

    def generate_dashboard(
        self, signals: List[Dict], regime: str, correlations: Dict
    ) -> str:
        """Generate comprehensive dashboard output"""
        output = []
        output.append("=" * 80)
        output.append("ENHANCED INTEGRATED SIGNAL DASHBOARD")
        output.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append(f"Market Regime: {regime.upper()}")
        output.append("=" * 80)

        # Sort by signal strength
        buy_signals = [s for s in signals if "BUY" in s["signal"]]
        sell_signals = [s for s in signals if "SELL" in s["signal"]]
        neutral_signals = [s for s in signals if s["signal"] == "NEUTRAL"]

        # Strong signals section
        output.append("\n🎯 STRONG SIGNALS (Confidence > 70%)")
        output.append("-" * 80)
        strong_signals = [s for s in signals if s["confidence"] > 70]
        if strong_signals:
            for s in sorted(
                strong_signals, key=lambda x: x["confidence"], reverse=True
            ):
                emoji = "🟢" if "BUY" in s["signal"] else "🔴"
                output.append(
                    f"{emoji} {s['symbol']:6} | {s['signal']:12} | "
                    f"Conf: {s['confidence']:5.1f}% | "
                    f"Score: {s['weighted_score']:5.1f} | "
                    f"${s['price']:>12,.2f}"
                )
        else:
            output.append("No strong signals at this time")

        # All signals table
        output.append("\n📊 ALL ASSETS ANALYSIS")
        output.append("-" * 80)
        output.append(
            f"{'Symbol':<8} {'Signal':<12} {'Conf%':<8} {'Score':<8} "
            f"{'Tech':<6} {'Sent':<6} {'Whale':<6} {'Mom':<6} {'Price':>14}"
        )
        output.append("-" * 80)

        for s in sorted(signals, key=lambda x: x["market_cap_rank"] or 999):
            tech = s["components"]["technical"]["score"]
            sent = s["components"]["sentiment"]["score"]
            whale = s["components"]["whale"]["score"]
            mom = s["components"]["momentum"]["score"]

            emoji = (
                "🟢"
                if "BUY" in s["signal"]
                else "🔴"
                if "SELL" in s["signal"]
                else "⚪"
            )

            output.append(
                f"{emoji}{s['symbol']:<7} {s['signal']:<12} "
                f"{s['confidence']:>5.1f}%  {s['weighted_score']:>5.1f}  "
                f"{tech:>4}  {sent:>4}  {whale:>4}  {mom:>4}  "
                f"${s['price']:>13,.2f}"
            )

        # Summary statistics
        output.append("\n📈 SUMMARY STATISTICS")
        output.append("-" * 80)
        output.append(f"Total Assets Analyzed: {len(signals)}")
        output.append(
            f"Buy Signals: {len(buy_signals)} ({len(buy_signals) / len(signals) * 100:.0f}%)"
        )
        output.append(
            f"Sell Signals: {len(sell_signals)} ({len(sell_signals) / len(signals) * 100:.0f}%)"
        )
        output.append(
            f"Neutral Signals: {len(neutral_signals)} ({len(neutral_signals) / len(signals) * 100:.0f}%)"
        )

        avg_confidence = statistics.mean([s["confidence"] for s in signals])
        output.append(f"Average Confidence: {avg_confidence:.1f}%")

        # Top opportunities
        output.append("\n🏆 TOP 3 OPPORTUNITIES")
        output.append("-" * 80)
        top_buys = sorted(buy_signals, key=lambda x: x["confidence"], reverse=True)[:3]
        for i, s in enumerate(top_buys, 1):
            output.append(
                f"{i}. {s['symbol']}: {s['signal']} "
                f"(Confidence: {s['confidence']:.1f}%, "
                f"Score: {s['weighted_score']:.1f})"
            )

        # Risk warnings
        output.append("\n⚠️  RISK ASSESSMENT")
        output.append("-" * 80)
        high_vol = [
            s
            for s in signals
            if s["components"]["technical"].get("signals", [])
            and any(
                "volatility" in str(sig).lower()
                for sig in s["components"]["technical"]["signals"]
            )
        ]
        if high_vol:
            output.append(
                f"High Volatility Assets: {', '.join([s['symbol'] for s in high_vol])}"
            )

        # Correlation insights
        output.append("\n🔗 CORRELATION INSIGHTS")
        output.append("-" * 80)
        if correlations:
            # Find most correlated pairs
            high_corr_pairs = []
            symbols = list(correlations.keys())
            for i in range(len(symbols)):
                for j in range(i + 1, len(symbols)):
                    corr = correlations[symbols[i]][symbols[j]]
                    if abs(corr) > 0.8:
                        high_corr_pairs.append((symbols[i], symbols[j], corr))

            if high_corr_pairs:
                output.append("Highly Correlated Pairs (>0.8):")
                for s1, s2, corr in sorted(
                    high_corr_pairs, key=lambda x: abs(x[2]), reverse=True
                )[:5]:
                    output.append(f"  {s1}-{s2}: {corr:.2f}")
            else:
                output.append("No highly correlated pairs detected")

        # Weight configuration
        output.append("\n⚙️  OPTIMIZED WEIGHTS (Regime: {})".format(regime.upper()))
        output.append("-" * 80)
        weights = OPTIMIZED_WEIGHTS[regime]
        output.append(f"Technical Analysis: {weights['technical'] * 100:.0f}%")
        output.append(f"Market Sentiment:   {weights['sentiment'] * 100:.0f}%")
        output.append(f"Whale Activity:     {weights['whale'] * 100:.0f}%")
        output.append(f"Price Momentum:     {weights['momentum'] * 100:.0f}%")

        output.append("\n" + "=" * 80)
        output.append(
            "DISCLAIMER: This is for educational purposes only, not financial advice."
        )
        output.append("=" * 80)

        return "\n".join(output)

    def _interpret_score(self, score: float) -> str:
        """Interpret a score value"""
        if score >= 70:
            return "Strong Bullish"
        elif score >= 60:
            return "Bullish"
        elif score >= 45:
            return "Neutral"
        elif score >= 35:
            return "Bearish"
        else:
            return "Strong Bearish"

    def _is_cached(self, key: str) -> bool:
        """Check if cache is valid"""
        if key in self.cache:
            return time.time() - self.cache[key]["timestamp"] < self.cache_ttl
        return False

    def _update_cache(self, key: str, data):
        """Update cache with new data"""
        self.cache[key] = {"data": data, "timestamp": time.time()}

    def run_analysis(self) -> Dict:
        """Run complete analysis"""
        print("Fetching market data...")
        market_data = self.get_market_data()

        if not market_data:
            print("Error: No market data available")
            return {}

        print(f"Analyzing {len(market_data)} assets...")

        # Determine market regime
        regime = self.determine_market_regime(market_data)
        print(f"Market regime detected: {regime}")

        # Calculate signals for each asset
        signals = []
        for coin in market_data:
            signal = self.calculate_integrated_signal(coin, regime)
            signals.append(signal)

        # Calculate correlations
        correlations = self.calculate_correlation_matrix(market_data)

        # Generate dashboard
        dashboard = self.generate_dashboard(signals, regime, correlations)

        # Save results
        results = {
            "timestamp": datetime.now().isoformat(),
            "regime": regime,
            "signals": signals,
            "correlations": correlations,
            "dashboard": dashboard,
        }

        with open("/opt/agent-memory-unified/data/enhanced_signals.json", "w") as f:
            json.dump(results, f, indent=2)

        print("\nResults saved to data/enhanced_signals.json")

        return results


def main():
    analyzer = EnhancedIntegratedSignal()
    results = analyzer.run_analysis()

    if results:
        print("\n" + results["dashboard"])


if __name__ == "__main__":
    main()
