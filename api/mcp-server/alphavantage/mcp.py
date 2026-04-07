from __future__ import annotations
import os
import sys
import asyncio
import logging
from typing import Optional

# Ensure we can import from project
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.append(PROJECT_ROOT)

from fastmcp import FastMCP
import httpx

# Initialize FastMCP
mcp = FastMCP("AlphaVantage")

logger = logging.getLogger("alphavantage_mcp")

@mcp.tool()
async def get_market_sentiment(ticker: str) -> str:
    """
    Fetch AI-powered news sentiment for a given ticker from Alpha Vantage.
    
    Args:
        ticker: The asset symbol (e.g. 'BTC', 'AAPL')
    """
    api_key = os.getenv("STA_ALPHA_VANTAGE_KEY")
    if not api_key:
        return "Error: STA_ALPHA_VANTAGE_KEY environment variable not set."
        
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker,
        "apikey": api_key
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            feed = data.get("feed", [])
            if not feed:
                return f"No sentiment data found for {ticker}."
                
            # Summarize top 3 news items
            summary = [f"Market Sentiment for {ticker}:"]
            for item in feed[:3]:
                title = item.get("title", "No Title")
                score = item.get("overall_sentiment_score", "0")
                label = item.get("overall_sentiment_label", "Neutral")
                summary.append(f"- {title} | Score: {score} ({label})")
                
            return "\n".join(summary)
            
    except Exception as e:
        return f"Request failed: {str(e)}"

@mcp.tool()
async def get_technical_indicators(ticker: str, interval: str = "daily") -> str:
    """
    Fetch basic technical indicators (RSI, SMA) for a ticker from Alpha Vantage.
    
    Args:
        ticker: The asset symbol
        interval: Time interval (1min, 5min, 15min, 30min, 60min, daily, weekly, monthly)
    """
    api_key = os.getenv("STA_ALPHA_VANTAGE_KEY")
    if not api_key:
        return "Error: STA_ALPHA_VANTAGE_KEY environment variable not set."

    # For simplicity in this tool, we fetch RSI
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "RSI",
        "symbol": ticker,
        "interval": interval,
        "time_period": 14,
        "series_type": "close",
        "apikey": api_key
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10.0)
            data = resp.json()
            
            # Key is "Technical Analysis: RSI"
            key = "Technical Analysis: RSI"
            if key not in data:
                return f"Error: Could not fetch technicals for {ticker}. Check API limits."
                
            last_refreshed = data.get("Meta Data", {}).get("3: Last Refreshed", "Unknown")
            # Get latest value
            latest_ts = next(iter(data[key]))
            latest_val = data[key][latest_ts]["RSI"]
            
            return f"Technical Update for {ticker} ({interval}): RSI is {latest_val} as of {latest_ts}."
            
    except Exception as e:
        return f"Request failed: {str(e)}"

if __name__ == "__main__":
    mcp.run()
