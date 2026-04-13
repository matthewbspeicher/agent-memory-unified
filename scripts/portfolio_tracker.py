#!/usr/bin/env python3
"""
Portfolio Tracker - Track cryptocurrency holdings across exchanges
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List
import ccxt.async_support as ccxt
import aiohttp


class PortfolioTracker:
    """Track portfolio across multiple exchanges with real-time pricing"""

    STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "TUSD"}

    COINGECKO_IDS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "AVAX": "avalanche-2",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "LINK": "chainlink",
        "UNI": "uniswap",
        "AAVE": "aave",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
        "LTC": "litecoin",
        "ATOM": "cosmos",
        "NEAR": "near",
    }

    def __init__(self):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.holdings: Dict = {}

    async def connect_exchange(
        self, exchange_id: str, api_key: str = None, secret: str = None
    ) -> bool:
        """Connect to an exchange. Returns True on success."""
        try:
            exchange_class = getattr(ccxt, exchange_id)
            config = {"enableRateLimit": True, "options": {"defaultType": "spot"}}

            if api_key and secret:
                config["apiKey"] = api_key
                config["secret"] = secret

            self.exchanges[exchange_id] = exchange_class(config)
            print(f"✅ Connected to {exchange_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to {exchange_id}: {e}")
            return False

    async def fetch_balances(self) -> Dict:
        """Fetch balances from all connected exchanges"""
        all_balances = {}

        for exchange_id, exchange in self.exchanges.items():
            try:
                balance = await exchange.fetch_balance()

                for asset, amounts in balance.items():
                    if asset in ("free", "used", "total", "info"):
                        continue

                    total = float(amounts.get("total", 0))
                    if total <= 0:
                        continue

                    if asset not in all_balances:
                        all_balances[asset] = {
                            "free": 0,
                            "used": 0,
                            "total": 0,
                            "exchanges": {},
                        }

                    all_balances[asset]["free"] += float(amounts.get("free", 0))
                    all_balances[asset]["used"] += float(amounts.get("used", 0))
                    all_balances[asset]["total"] += total
                    all_balances[asset]["exchanges"][exchange_id] = {
                        "free": float(amounts.get("free", 0)),
                        "used": float(amounts.get("used", 0)),
                        "total": total,
                    }
            except Exception as e:
                print(f"⚠️ Error fetching balances from {exchange_id}: {e}")

        self.holdings = all_balances
        return all_balances

    async def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get current USD prices for symbols"""
        prices = {}

        if not self.exchanges:
            return await self._fetch_prices_coingecko(symbols)

        exchange = list(self.exchanges.values())[0]

        for symbol in symbols:
            for pair in [f"{symbol}/USDT", f"{symbol}/USD"]:
                try:
                    ticker = await exchange.fetch_ticker(pair)
                    prices[symbol.upper()] = ticker["last"]
                    break
                except Exception:
                    continue

        return prices

    async def _fetch_prices_coingecko(self, symbols: List[str]) -> Dict[str, float]:
        """Fallback price fetch from CoinGecko"""
        prices = {}
        ids = ",".join(self.COINGECKO_IDS.get(s.upper(), s.lower()) for s in symbols)

        async with aiohttp.ClientSession() as session:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    for symbol in symbols:
                        cg_id = self.COINGECKO_IDS.get(symbol.upper(), symbol.lower())
                        if cg_id in data:
                            prices[symbol.upper()] = data[cg_id]["usd"]

        return prices

    async def calculate_portfolio_value(self) -> Dict:
        """Calculate total portfolio value with asset breakdown"""
        balances = await self.fetch_balances()
        assets_to_price = [a for a in balances if a not in self.STABLECOINS]

        prices = await self.get_prices(assets_to_price)

        total_value = 0
        asset_values = {}

        for asset, balance in balances.items():
            if asset in self.STABLECOINS:
                value = balance["total"]
            else:
                value = balance["total"] * prices.get(asset, 0)

            asset_values[asset] = {
                "amount": balance["total"],
                "price": prices.get(asset, 1.0 if asset in self.STABLECOINS else 0),
                "value_usd": value,
                "percentage": 0,
            }
            total_value += value

        for asset in asset_values:
            if total_value > 0:
                asset_values[asset]["percentage"] = (
                    asset_values[asset]["value_usd"] / total_value
                ) * 100

        return {
            "timestamp": datetime.now().isoformat(),
            "total_value_usd": total_value,
            "assets": asset_values,
            "exchange_breakdown": self._calculate_exchange_values(balances, prices),
        }

    def _calculate_exchange_values(self, balances: Dict, prices: Dict) -> Dict:
        """Calculate value held on each exchange"""
        exchange_values = {}

        for asset, balance in balances.items():
            for exchange_id, amounts in balance.get("exchanges", {}).items():
                if exchange_id not in exchange_values:
                    exchange_values[exchange_id] = 0

                if asset in self.STABLECOINS:
                    value = amounts["total"]
                else:
                    value = amounts["total"] * prices.get(asset, 0)

                exchange_values[exchange_id] += value

        return exchange_values

    def generate_report(self, portfolio_data: Dict) -> str:
        """Generate formatted portfolio report"""
        lines = [
            "=" * 60,
            "📊 PORTFOLIO REPORT",
            f"Generated: {portfolio_data['timestamp']}",
            "=" * 60,
            f"\n💰 Total Portfolio Value: ${portfolio_data['total_value_usd']:,.2f}",
            "\n📈 Asset Allocation:",
            "-" * 60,
        ]

        sorted_assets = sorted(
            portfolio_data["assets"].items(),
            key=lambda x: x[1]["value_usd"],
            reverse=True,
        )

        for asset, data in sorted_assets:
            if data["value_usd"] <= 0:
                continue

            bar_length = int(data["percentage"] / 5)
            bar = "█" * bar_length + "░" * (20 - bar_length)

            lines.append(
                f"{asset:8} | ${data['value_usd']:>12,.2f} | "
                f"{data['percentage']:>5.1f}% | {bar} | "
                f"{data['amount']:>12.4f} @ ${data['price']:,.2f}"
            )

        lines.append("\n🏦 Exchange Breakdown:")
        lines.append("-" * 60)

        for exchange, value in portfolio_data["exchange_breakdown"].items():
            pct = (
                (value / portfolio_data["total_value_usd"]) * 100
                if portfolio_data["total_value_usd"] > 0
                else 0
            )
            lines.append(f"{exchange:15} | ${value:>12,.2f} | {pct:>5.1f}%")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    async def close(self):
        """Close all exchange connections"""
        for exchange in self.exchanges.values():
            await exchange.close()


async def main():
    """Run portfolio tracker"""
    print("🚀 Portfolio Tracker - Phase 1, Day 3-4")
    print("=" * 60)

    tracker = PortfolioTracker()
    await tracker.connect_exchange("binance")
    await tracker.connect_exchange("coinbase")

    print("\n📡 Fetching portfolio data...")
    portfolio_data = await tracker.calculate_portfolio_value()

    report = tracker.generate_report(portfolio_data)
    print(report)

    with open("/opt/agent-memory-unified/data/portfolio_snapshot.json", "w") as f:
        json.dump(portfolio_data, f, indent=2)
    print(f"\n💾 Snapshot saved to data/portfolio_snapshot.json")

    await tracker.close()


if __name__ == "__main__":
    asyncio.run(main())
