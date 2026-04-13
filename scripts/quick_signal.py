#!/usr/bin/env python3
"""
Quick Technical Signal - Analyze single asset
"""

import asyncio
import json
from datetime import datetime
import aiohttp
import numpy as np


async def analyze_asset(symbol: str):
    """Analyze single asset"""
    print(f"\n📡 Analyzing {symbol}...")

    # Fetch price history
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": 100,
        "interval": "daily",
        "x_cg_demo_api_key": "CG-oL81mP8oWpvHM1JMiXN5chEC",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                print(f"Failed to fetch data for {symbol}")
                return

            data = await response.json()
            prices = [p[1] for p in data["prices"]]

    current_price = prices[-1]

    # Calculate RSI
    deltas = np.diff(prices[-15:])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains) if len(gains) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0.001
    rsi = 100 - (100 / (1 + avg_gain / avg_loss))

    # Calculate SMAs
    sma_20 = np.mean(prices[-20:])
    sma_50 = np.mean(prices[-50:]) if len(prices) >= 50 else np.mean(prices)

    # Calculate Bollinger Bands
    bb_middle = sma_20
    bb_std = np.std(prices[-20:])
    bb_upper = bb_middle + (bb_std * 2)
    bb_lower = bb_middle - (bb_std * 2)
    bb_percent = (
        (current_price - bb_lower) / (bb_upper - bb_lower)
        if bb_upper != bb_lower
        else 0.5
    )

    # Generate signal
    score = 0
    signals = []

    # RSI
    if rsi < 30:
        signals.append(f"🟢 RSI Oversold ({rsi:.1f})")
        score += 2
    elif rsi > 70:
        signals.append(f"🔴 RSI Overbought ({rsi:.1f})")
        score -= 2
    else:
        signals.append(f"⚪ RSI Neutral ({rsi:.1f})")

    # MA Cross
    if sma_20 > sma_50:
        signals.append(f"🟢 Golden Cross (SMA20 > SMA50)")
        score += 2
    else:
        signals.append(f"🔴 Death Cross (SMA20 < SMA50)")
        score -= 2

    # Price vs Bollinger
    if bb_percent < 0.2:
        signals.append(f"🟢 Near Lower Bollinger Band ({bb_percent:.2f})")
        score += 1
    elif bb_percent > 0.8:
        signals.append(f"🔴 Near Upper Bollinger Band ({bb_percent:.2f})")
        score -= 1

    # Determine direction
    if score >= 3:
        direction = "STRONG BUY"
    elif score >= 1:
        direction = "BUY"
    elif score <= -3:
        direction = "STRONG SELL"
    elif score <= -1:
        direction = "SELL"
    else:
        direction = "HOLD"

    # Print report
    print(f"\n{'=' * 60}")
    print(f"📊 {symbol.upper()} TECHNICAL ANALYSIS")
    print(f"{'=' * 60}")
    print(f"💰 Price: ${current_price:,.2f}")
    print(f"🎯 Signal: {direction}")
    print(f"📈 Score: {score:+d}")
    print(f"\n📉 Indicators:")
    for s in signals:
        print(f"  {s}")
    print(f"\n📊 Key Levels:")
    print(f"  SMA 20: ${sma_20:,.2f}")
    print(f"  SMA 50: ${sma_50:,.2f}")
    print(f"  BB Upper: ${bb_upper:,.2f}")
    print(f"  BB Lower: ${bb_lower:,.2f}")
    print(f"{'=' * 60}")

    return {
        "symbol": symbol,
        "price": current_price,
        "direction": direction,
        "score": score,
        "rsi": rsi,
        "sma_20": sma_20,
        "sma_50": sma_50,
    }


async def main():
    print("🚀 Quick Technical Signal Generator")
    print("=" * 60)

    assets = ["bitcoin", "ethereum", "solana"]
    results = []

    for asset in assets:
        result = await analyze_asset(asset)
        if result:
            results.append(result)

    # Summary
    print(f"\n{'=' * 60}")
    print("📊 SIGNAL SUMMARY")
    print(f"{'=' * 60}")
    for r in results:
        emoji = (
            "🟢"
            if "BUY" in r["direction"]
            else "🔴"
            if "SELL" in r["direction"]
            else "⚪"
        )
        print(
            f"{emoji} {r['symbol'].upper():10} ${r['price']:>10,.2f} → {r['direction']}"
        )
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
