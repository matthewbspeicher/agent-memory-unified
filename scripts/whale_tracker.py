#!/usr/bin/env python3
"""Whale Tracker - Monitors large transactions and exchange flows"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from decimal import Decimal
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class WhaleTransaction:
    tx_hash: str
    chain: str
    from_address: str
    to_address: str
    value_usd: float
    token_symbol: str
    timestamp: datetime
    transaction_type: str
    exchange_name: Optional[str] = None
    severity_score: int = 0


@dataclass
class ExchangeFlow:
    exchange: str
    chain: str
    deposits_usd: float
    withdrawals_usd: float
    net_flow_usd: float
    deposit_count: int
    withdrawal_count: int
    sentiment: str


class WhaleTracker:
    EXCHANGE_WALLETS = {
        "ethereum": {
            "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": "Binance",
            "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
            "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
            "0x564286362092d8e7936f0549571a803b203aaced": "Binance",
            "0x0681d8db095565fe8a346fa0277bffde9c0edbbf": "Binance",
            "0x4e9ce36e442e55ecd9025b9a6e0d88485d628a67": "Binance",
            "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
            "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
            "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740": "Coinbase",
            "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
            "0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13": "Kraken",
            "0x9848e002b79e6e7e7e7e7e7e7e7e7e7e7e7e7e7e": "OKX",
        }
    }

    WHALE_THRESHOLDS = {
        "BTC": 10,
        "ETH": 1000,
        "USDT": 1000000,
        "USDC": 1000000,
    }

    def __init__(self, coingecko_api_key: str = None):
        self.coingecko_api_key = coingecko_api_key
        self.session = None
        self.price_cache = {}
        self.transactions = []
        self.exchange_flows = {}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_token_price(self, symbol: str) -> float:
        if symbol in self.price_cache:
            cached = self.price_cache[symbol]
            if (datetime.now() - cached["timestamp"]).seconds < 60:
                return cached["price"]

        cg_ids = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "USDT": "tether",
            "USDC": "usd-coin",
            "BNB": "binancecoin",
            "SOL": "solana",
            "XRP": "ripple",
            "ADA": "cardano",
            "DOGE": "dogecoin",
            "DOT": "polkadot",
        }

        cg_id = cg_ids.get(symbol.upper(), symbol.lower())

        try:
            url = f"https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": cg_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if cg_id in data:
                        price = data[cg_id]["usd"]
                        self.price_cache[symbol] = {
                            "price": price,
                            "timestamp": datetime.now(),
                        }
                        return price
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")

        fallback_prices = {
            "BTC": 73123.0,
            "ETH": 2248.0,
            "SOL": 84.87,
            "USDT": 1.0,
            "USDC": 1.0,
        }
        return fallback_prices.get(symbol.upper(), 0.0)

    def identify_exchange(self, address: str, chain: str = "ethereum") -> Optional[str]:
        wallets = self.EXCHANGE_WALLETS.get(chain, {})
        return wallets.get(address.lower())

    def classify_transaction(
        self, from_exchange: Optional[str], to_exchange: Optional[str]
    ) -> str:
        if to_exchange and not from_exchange:
            return "exchange_deposit"
        elif from_exchange and not to_exchange:
            return "exchange_withdrawal"
        elif from_exchange and to_exchange:
            return "exchange_to_exchange"
        return "wallet_transfer"

    def calculate_severity_score(self, value_usd: float, tx_type: str) -> int:
        score = 0
        if value_usd > 50_000_000:
            score += 50
        elif value_usd > 10_000_000:
            score += 40
        elif value_usd > 5_000_000:
            score += 30
        elif value_usd > 1_000_000:
            score += 20
        else:
            score += 10

        if tx_type == "exchange_deposit":
            score += 20
        elif tx_type == "exchange_withdrawal":
            score += 10

        return min(score, 100)

    async def analyze_whale_alert(self, alert_data: Dict) -> Optional[WhaleTransaction]:
        try:
            symbol = alert_data.get("symbol", "UNKNOWN")
            value_usd = float(alert_data.get("amount_usd", 0))
            from_address = alert_data.get("from", {}).get("address", "")
            to_address = alert_data.get("to", {}).get("address", "")

            if value_usd == 0 and symbol != "UNKNOWN":
                price = await self.get_token_price(symbol)
                amount = float(alert_data.get("amount", 0))
                value_usd = amount * price

            from_exchange = self.identify_exchange(from_address)
            to_exchange = self.identify_exchange(to_address)
            tx_type = self.classify_transaction(from_exchange, to_exchange)
            severity = self.calculate_severity_score(value_usd, tx_type)

            tx = WhaleTransaction(
                tx_hash=alert_data.get("hash", ""),
                chain=alert_data.get("blockchain", "ethereum"),
                from_address=from_address,
                to_address=to_address,
                value_usd=value_usd,
                token_symbol=symbol,
                timestamp=datetime.now(),
                transaction_type=tx_type,
                exchange_name=to_exchange or from_exchange,
                severity_score=severity,
            )

            self.transactions.append(tx)
            return tx

        except Exception as e:
            logger.error(f"Error analyzing whale alert: {e}")
            return None

    def update_exchange_flows(self, tx: WhaleTransaction):
        if not tx.exchange_name:
            return

        key = f"{tx.exchange_name}:{tx.chain}"

        if key not in self.exchange_flows:
            self.exchange_flows[key] = ExchangeFlow(
                exchange=tx.exchange_name,
                chain=tx.chain,
                deposits_usd=0,
                withdrawals_usd=0,
                net_flow_usd=0,
                deposit_count=0,
                withdrawal_count=0,
                sentiment="neutral",
            )

        flow = self.exchange_flows[key]

        if tx.transaction_type == "exchange_deposit":
            flow.deposits_usd += tx.value_usd
            flow.deposit_count += 1
        elif tx.transaction_type == "exchange_withdrawal":
            flow.withdrawals_usd += tx.value_usd
            flow.withdrawal_count += 1

        flow.net_flow_usd = flow.withdrawals_usd - flow.deposits_usd

        if flow.net_flow_usd > 10_000_000:
            flow.sentiment = "bullish"
        elif flow.net_flow_usd < -10_000_000:
            flow.sentiment = "bearish"
        else:
            flow.sentiment = "neutral"

    def get_whale_summary(self) -> Dict:
        if not self.transactions:
            return {"status": "no_data", "transactions": 0}

        recent_cutoff = datetime.now() - timedelta(hours=24)
        recent_txs = [tx for tx in self.transactions if tx.timestamp > recent_cutoff]

        total_volume = sum(tx.value_usd for tx in recent_txs)
        deposits = [
            tx for tx in recent_txs if tx.transaction_type == "exchange_deposit"
        ]
        withdrawals = [
            tx for tx in recent_txs if tx.transaction_type == "exchange_withdrawal"
        ]

        deposit_volume = sum(tx.value_usd for tx in deposits)
        withdrawal_volume = sum(tx.value_usd for tx in withdrawals)
        net_flow = withdrawal_volume - deposit_volume

        if net_flow > 50_000_000:
            sentiment = "BULLISH"
            sentiment_score = 70
        elif net_flow > 10_000_000:
            sentiment = "SLIGHTLY_BULLISH"
            sentiment_score = 60
        elif net_flow < -50_000_000:
            sentiment = "BEARISH"
            sentiment_score = 30
        elif net_flow < -10_000_000:
            sentiment = "SLIGHTLY_BEARISH"
            sentiment_score = 40
        else:
            sentiment = "NEUTRAL"
            sentiment_score = 50

        largest_txs = sorted(recent_txs, key=lambda x: x.value_usd, reverse=True)[:5]

        return {
            "status": "active",
            "timestamp": datetime.now().isoformat(),
            "period": "24h",
            "total_transactions": len(recent_txs),
            "total_volume_usd": total_volume,
            "exchange_flows": {
                "deposits_usd": deposit_volume,
                "withdrawals_usd": withdrawal_volume,
                "net_flow_usd": net_flow,
                "deposit_count": len(deposits),
                "withdrawal_count": len(withdrawals),
            },
            "sentiment": {
                "label": sentiment,
                "score": sentiment_score,
                "interpretation": self._interpret_whale_sentiment(sentiment_score),
            },
            "largest_transactions": [
                {
                    "value_usd": tx.value_usd,
                    "symbol": tx.token_symbol,
                    "type": tx.transaction_type,
                    "exchange": tx.exchange_name,
                    "severity": tx.severity_score,
                }
                for tx in largest_txs
            ],
            "exchange_flow_details": {
                key: {
                    "exchange": flow.exchange,
                    "net_flow_usd": flow.net_flow_usd,
                    "sentiment": flow.sentiment,
                }
                for key, flow in self.exchange_flows.items()
            },
        }

    def _interpret_whale_sentiment(self, score: int) -> str:
        if score >= 70:
            return "Whales accumulating - moving assets off exchanges (bullish)"
        elif score >= 60:
            return "Slight accumulation trend - net outflows from exchanges"
        elif score <= 30:
            return "Whales distributing - moving assets to exchanges (bearish)"
        elif score <= 40:
            return "Slight distribution trend - net inflows to exchanges"
        else:
            return "Balanced flows - no clear whale direction"


async def simulate_whale_data(tracker: WhaleTracker):
    simulated_txs = [
        {
            "hash": "0xabc123...",
            "blockchain": "ethereum",
            "symbol": "ETH",
            "amount": 5000,
            "amount_usd": 11240000,
            "from": {"address": "0x71660c4005ba85c37ccec55d0c4493e66fe775d3"},
            "to": {"address": "0x1234567890abcdef1234567890abcdef12345678"},
        },
        {
            "hash": "0xdef456...",
            "blockchain": "ethereum",
            "symbol": "ETH",
            "amount": 8000,
            "amount_usd": 17984000,
            "from": {"address": "0xabcdef1234567890abcdef1234567890abcdef12"},
            "to": {"address": "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be"},
        },
        {
            "hash": "0x789abc...",
            "blockchain": "ethereum",
            "symbol": "USDT",
            "amount": 25000000,
            "amount_usd": 25000000,
            "from": {"address": "0x28c6c06298d514db089934071355e5743bf21d60"},
            "to": {"address": "0x503828976d22510aad0201ac7ec88293211d23da"},
        },
        {
            "hash": "0xdef012...",
            "blockchain": "ethereum",
            "symbol": "ETH",
            "amount": 12000,
            "amount_usd": 26976000,
            "from": {"address": "0x9876543210fedcba9876543210fedcba98765432"},
            "to": {"address": "0x71660c4005ba85c37ccec55d0c4493e66fe775d3"},
        },
        {
            "hash": "0x345678...",
            "blockchain": "ethereum",
            "symbol": "ETH",
            "amount": 3500,
            "amount_usd": 7868000,
            "from": {"address": "0x2910543af39aba0cd09dbb2d50200b3e800a63d2"},
            "to": {"address": "0xfedcba0987654321fedcba0987654321fedcba09"},
        },
    ]

    for tx_data in simulated_txs:
        tx = await tracker.analyze_whale_alert(tx_data)
        if tx:
            tracker.update_exchange_flows(tx)
            logger.info(
                f"Processed: {tx.value_usd:,.0f} {tx.token_symbol} - {tx.transaction_type}"
            )


async def main():
    print("=" * 70)
    print("🐋 WHALE TRACKER - Day 11-12 Implementation")
    print("=" * 70)
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)

    async with WhaleTracker() as tracker:
        print("\n📊 Simulating whale transactions...")
        await simulate_whale_data(tracker)

        summary = tracker.get_whale_summary()

        print("\n" + "=" * 70)
        print("📈 WHALE ACTIVITY SUMMARY (24h)")
        print("=" * 70)

        print(f"\n📊 Transaction Statistics:")
        print(f"   Total Transactions: {summary['total_transactions']}")
        print(f"   Total Volume: ${summary['total_volume_usd']:,.0f}")

        print(f"\n💰 Exchange Flows:")
        flows = summary["exchange_flows"]
        print(
            f"   Deposits (to exchanges):   ${flows['deposits_usd']:,.0f} ({flows['deposit_count']} txs)"
        )
        print(
            f"   Withdrawals (off exchanges): ${flows['withdrawals_usd']:,.0f} ({flows['withdrawal_count']} txs)"
        )
        print(f"   Net Flow: ${flows['net_flow_usd']:,.0f}")

        if flows["net_flow_usd"] > 0:
            print(f"   → Net OUTFLOW (bullish) - whales moving assets off exchanges")
        else:
            print(f"   → Net INFLOW (bearish) - whales moving assets to exchanges")

        print(f"\n🎯 Whale Sentiment:")
        sentiment = summary["sentiment"]
        print(f"   Label: {sentiment['label']}")
        print(f"   Score: {sentiment['score']}/100")
        print(f"   Interpretation: {sentiment['interpretation']}")

        print(f"\n🏆 Largest Transactions:")
        for i, tx in enumerate(summary["largest_transactions"][:3], 1):
            print(f"   {i}. ${tx['value_usd']:,.0f} {tx['symbol']} - {tx['type']}")
            if tx["exchange"]:
                print(f"      Exchange: {tx['exchange']}")

        print(f"\n🏦 Exchange Flow Details:")
        for key, details in summary["exchange_flow_details"].items():
            print(
                f"   {details['exchange']}: ${details['net_flow_usd']:,.0f} ({details['sentiment']})"
            )

        output_file = "/opt/agent-memory-unified/data/whale_analysis.json"
        with open(output_file, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\n💾 Results saved to: {output_file}")

        print("\n" + "=" * 70)
        print("✅ Whale tracking complete!")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
