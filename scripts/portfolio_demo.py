#!/usr/bin/env python3
"""
Portfolio Tracker Demo - Shows functionality with sample data
"""

import asyncio
import json
from datetime import datetime
import aiohttp


class PortfolioDemo:
    """Demo portfolio tracker using CoinGecko public API"""

    STABLECOINS = {"USDT", "USDC", "DAI"}

    COINGECKO_IDS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "AVAX": "avalanche-2",
        "DOT": "polkadot",
        "LINK": "chainlink",
        "MATIC": "matic-network",
        "UNI": "uniswap",
    }

    def __init__(self):
        self.sample_holdings = {
            "BTC": {"amount": 0.5, "avg_cost": 42000},
            "ETH": {"amount": 5.0, "avg_cost": 2200},
            "SOL": {"amount": 50.0, "avg_cost": 85},
            "AVAX": {"amount": 100.0, "avg_cost": 28},
            "USDC": {"amount": 10000, "avg_cost": 1.0},
        }

    async def get_prices(self, symbols):
        """Fetch prices from CoinGecko"""
        ids = ",".join(self.COINGECKO_IDS.get(s, s.lower()) for s in symbols)
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
        return {}

    async def calculate_portfolio(self):
        """Calculate portfolio value"""
        assets_to_price = [s for s in self.sample_holdings if s not in self.STABLECOINS]
        prices = await self.get_prices(assets_to_price)

        total_value = 0
        total_cost = 0
        asset_data = []

        for symbol, holding in self.sample_holdings.items():
            if symbol in self.STABLECOINS:
                price = 1.0
                change_24h = 0
            else:
                cg_id = self.COINGECKO_IDS.get(symbol, symbol.lower())
                price = prices.get(cg_id, {}).get("usd", 0)
                change_24h = prices.get(cg_id, {}).get("usd_24h_change", 0)

            value = holding["amount"] * price
            cost = holding["amount"] * holding["avg_cost"]
            pnl = value - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0

            total_value += value
            total_cost += cost

            asset_data.append(
                {
                    "symbol": symbol,
                    "amount": holding["amount"],
                    "price": price,
                    "value": value,
                    "cost": cost,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "change_24h": change_24h,
                    "allocation": 0,
                }
            )

        for asset in asset_data:
            asset["allocation"] = (
                (asset["value"] / total_value * 100) if total_value > 0 else 0
            )

        return {
            "timestamp": datetime.now().isoformat(),
            "total_value": total_value,
            "total_cost": total_cost,
            "total_pnl": total_value - total_cost,
            "total_pnl_pct": ((total_value - total_cost) / total_cost * 100)
            if total_cost > 0
            else 0,
            "assets": sorted(asset_data, key=lambda x: x["value"], reverse=True),
        }

    def generate_report(self, data):
        """Generate formatted report"""
        lines = [
            "=" * 70,
            "📊 PORTFOLIO REPORT - DEMO",
            f"Generated: {data['timestamp']}",
            "=" * 70,
            "",
            f"💰 Total Value:  ${data['total_value']:>14,.2f}",
            f"📈 Total P&L:    ${data['total_pnl']:>14,.2f} ({data['total_pnl_pct']:+.2f}%)",
            f"💵 Total Cost:   ${data['total_cost']:>14,.2f}",
            "",
            "-" * 70,
            f"{'Asset':8} {'Amount':>12} {'Price':>10} {'Value':>14} {'P&L':>14} {'24h':>8} {'Alloc':>6}",
            "-" * 70,
        ]

        for asset in data["assets"]:
            pnl_indicator = "🟢" if asset["pnl"] >= 0 else "🔴"
            change_indicator = "📈" if asset["change_24h"] >= 0 else "📉"

            lines.append(
                f"{asset['symbol']:8} "
                f"{asset['amount']:>12.4f} "
                f"${asset['price']:>9,.2f} "
                f"${asset['value']:>13,.2f} "
                f"{pnl_indicator}${abs(asset['pnl']):>12,.2f} "
                f"{change_indicator}{asset['change_24h']:>+6.2f}% "
                f"{asset['allocation']:>5.1f}%"
            )

        lines.extend(["-" * 70, "", "📈 Allocation Chart:", ""])

        for asset in data["assets"][:5]:
            bar_length = int(asset["allocation"] / 2)
            bar = "█" * bar_length
            lines.append(f"  {asset['symbol']:6} {bar} {asset['allocation']:.1f}%")

        lines.extend(["", "=" * 70])
        return "\n".join(lines)


async def main():
    print("🚀 Portfolio Tracker Demo - Phase 1, Day 3-4")
    print("=" * 60)

    demo = PortfolioDemo()
    portfolio_data = await demo.calculate_portfolio()

    report = demo.generate_report(portfolio_data)
    print(report)

    with open("/opt/agent-memory-unified/data/portfolio_demo.json", "w") as f:
        json.dump(portfolio_data, f, indent=2, default=str)
    print(f"\n💾 Saved to data/portfolio_demo.json")


if __name__ == "__main__":
    asyncio.run(main())
