#!/usr/bin/env python3
"""
Market Sentiment Monitor - Fear & Greed Index and sentiment analysis
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List
import aiohttp


class SentimentMonitor:
    """Monitor market sentiment using multiple data sources"""

    def __init__(self, coingecko_api_key: str = None):
        self.api_key = coingecko_api_key
        self.fear_greed_history = []

    async def get_fear_greed_index(self) -> Dict:
        """Fetch Fear & Greed Index from Alternative.me"""
        url = "https://api.alternative.me/fng/?limit=1"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    fng_data = data["data"][0]

                    return {
                        "value": int(fng_data["value"]),
                        "classification": fng_data["value_classification"],
                        "timestamp": datetime.fromtimestamp(
                            int(fng_data["timestamp"])
                        ).isoformat(),
                    }

        return {
            "value": 50,
            "classification": "Neutral",
            "timestamp": datetime.now().isoformat(),
        }

    async def get_market_data(self) -> Dict:
        """Fetch overall crypto market data"""
        url = "https://api.coingecko.com/api/v3/global"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    global_data = data["data"]

                    return {
                        "total_market_cap": global_data["total_market_cap"]["usd"],
                        "total_volume": global_data["total_volume"]["usd"],
                        "btc_dominance": global_data["market_cap_percentage"]["btc"],
                        "eth_dominance": global_data["market_cap_percentage"]["eth"],
                        "market_cap_change_24h": global_data[
                            "market_cap_change_percentage_24h_usd"
                        ],
                    }

        return {}

    async def get_bitcoin_data(self) -> Dict:
        """Fetch Bitcoin-specific data for sentiment analysis"""
        url = "https://api.coingecko.com/api/v3/coins/bitcoin"
        params = {
            "localization": "false",
            "tickers": "false",
            "community_data": "true",
            "developer_data": "true",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    return {
                        "price": data["market_data"]["current_price"]["usd"],
                        "price_change_24h": data["market_data"][
                            "price_change_percentage_24h"
                        ],
                        "price_change_7d": data["market_data"][
                            "price_change_percentage_7d"
                        ],
                        "price_change_30d": data["market_data"][
                            "price_change_percentage_30d"
                        ],
                        "market_cap": data["market_data"]["market_cap"]["usd"],
                        "volume_24h": data["market_data"]["total_volume"]["usd"],
                        "ath": data["market_data"]["ath"]["usd"],
                        "ath_change_percentage": data["market_data"][
                            "ath_change_percentage"
                        ]["usd"],
                        "social_stats": {
                            "twitter_followers": data.get("community_data", {}).get(
                                "twitter_followers", 0
                            ),
                            "reddit_subscribers": data.get("community_data", {}).get(
                                "reddit_subscribers", 0
                            ),
                        },
                    }

        return {}

    def calculate_sentiment_score(
        self, fear_greed: Dict, market_data: Dict, btc_data: Dict
    ) -> Dict:
        """Calculate composite sentiment score"""
        score = 0
        factors = []

        # Fear & Greed Index (40% weight)
        fng_score = fear_greed["value"]
        score += fng_score * 0.4
        factors.append(
            {
                "name": "Fear & Greed Index",
                "value": fng_score,
                "weight": 0.4,
                "contribution": fng_score * 0.4,
            }
        )

        # Price momentum (30% weight)
        if btc_data:
            momentum = 0
            if btc_data.get("price_change_24h", 0) > 0:
                momentum += 20
            if btc_data.get("price_change_7d", 0) > 0:
                momentum += 30
            if btc_data.get("price_change_30d", 0) > 0:
                momentum += 50

            score += momentum * 0.3
            factors.append(
                {
                    "name": "Price Momentum",
                    "value": momentum,
                    "weight": 0.3,
                    "contribution": momentum * 0.3,
                }
            )

        # Market cap change (20% weight)
        if market_data:
            mcap_change = market_data.get("market_cap_change_24h", 0)
            mcap_score = min(max((mcap_change + 5) * 10, 0), 100)
            score += mcap_score * 0.2
            factors.append(
                {
                    "name": "Market Cap Change",
                    "value": mcap_score,
                    "weight": 0.2,
                    "contribution": mcap_score * 0.2,
                }
            )

        # BTC dominance (10% weight)
        if market_data:
            btc_dom = market_data.get("btc_dominance", 50)
            dom_score = 100 - abs(btc_dom - 50) * 2
            score += dom_score * 0.1
            factors.append(
                {
                    "name": "BTC Dominance Stability",
                    "value": dom_score,
                    "weight": 0.1,
                    "contribution": dom_score * 0.1,
                }
            )

        # Determine sentiment level
        if score >= 75:
            level = "Extreme Greed"
            action = "Consider taking profits - market may be overheated"
        elif score >= 55:
            level = "Greed"
            action = "Market is bullish - ride the trend with caution"
        elif score >= 45:
            level = "Neutral"
            action = "Balanced market - wait for clearer signals"
        elif score >= 25:
            level = "Fear"
            action = "Potential buying opportunity - accumulate gradually"
        else:
            level = "Extreme Fear"
            action = "Strong buying opportunity - consider DCA"

        return {
            "composite_score": round(score, 1),
            "level": level,
            "action": action,
            "factors": factors,
            "timestamp": datetime.now().isoformat(),
        }

    def generate_report(
        self, fear_greed: Dict, market_data: Dict, btc_data: Dict, sentiment: Dict
    ) -> str:
        """Generate formatted sentiment report"""
        lines = [
            "=" * 70,
            "📊 MARKET SENTIMENT REPORT",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 70,
            "",
            "🎯 FEAR & GREED INDEX",
            "-" * 70,
            f"  Current Value: {fear_greed['value']}/100",
            f"  Classification: {fear_greed['classification']}",
            "",
        ]

        # Visual gauge
        gauge_value = fear_greed["value"]
        gauge_length = 50
        filled = int(gauge_value / 100 * gauge_length)
        gauge = "█" * filled + "░" * (gauge_length - filled)
        lines.append(f"  Fear [{gauge}] Greed")
        lines.append("")

        # Market data
        if market_data:
            lines.extend(
                [
                    "📈 MARKET OVERVIEW",
                    "-" * 70,
                    f"  Total Market Cap: ${market_data.get('total_market_cap', 0):,.0f}",
                    f"  24h Volume: ${market_data.get('total_volume', 0):,.0f}",
                    f"  Market Cap Change (24h): {market_data.get('market_cap_change_24h', 0):+.2f}%",
                    f"  BTC Dominance: {market_data.get('btc_dominance', 0):.1f}%",
                    f"  ETH Dominance: {market_data.get('eth_dominance', 0):.1f}%",
                    "",
                ]
            )

        # Bitcoin data
        if btc_data:
            lines.extend(
                [
                    "₿ BITCOIN METRICS",
                    "-" * 70,
                    f"  Price: ${btc_data.get('price', 0):,.2f}",
                    f"  24h Change: {btc_data.get('price_change_24h', 0):+.2f}%",
                    f"  7d Change: {btc_data.get('price_change_7d', 0):+.2f}%",
                    f"  30d Change: {btc_data.get('price_change_30d', 0):+.2f}%",
                    f"  ATH: ${btc_data.get('ath', 0):,.2f} ({btc_data.get('ath_change_percentage', 0):+.1f}%)",
                    "",
                ]
            )

        # Composite sentiment
        lines.extend(
            [
                "🧠 COMPOSITE SENTIMENT ANALYSIS",
                "-" * 70,
                f"  Score: {sentiment['composite_score']}/100",
                f"  Level: {sentiment['level']}",
                f"  Recommended Action: {sentiment['action']}",
                "",
                "  Factor Breakdown:",
            ]
        )

        for factor in sentiment["factors"]:
            bar_length = int(factor["contribution"] / 5)
            bar = "█" * bar_length + "░" * (20 - bar_length)
            lines.append(
                f"    {factor['name']:25} {factor['value']:5.0f} "
                f"(×{factor['weight']:.1f}) = {factor['contribution']:5.1f} {bar}"
            )

        lines.extend(["", "=" * 70])
        return "\n".join(lines)


async def main():
    """Run sentiment monitor"""
    print("🚀 Market Sentiment Monitor - Phase 1, Day 5-7")
    print("=" * 60)

    monitor = SentimentMonitor()

    print("\n📡 Fetching market data...")

    # Fetch all data concurrently
    fear_greed, market_data, btc_data = await asyncio.gather(
        monitor.get_fear_greed_index(),
        monitor.get_market_data(),
        monitor.get_bitcoin_data(),
    )

    # Calculate sentiment
    sentiment = monitor.calculate_sentiment_score(fear_greed, market_data, btc_data)

    # Generate report
    report = monitor.generate_report(fear_greed, market_data, btc_data, sentiment)
    print(report)

    # Save data
    output = {
        "fear_greed_index": fear_greed,
        "market_data": market_data,
        "bitcoin_data": btc_data,
        "composite_sentiment": sentiment,
    }

    with open("/opt/agent-memory-unified/data/sentiment_snapshot.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n💾 Saved to data/sentiment_snapshot.json")


if __name__ == "__main__":
    asyncio.run(main())
