import os
import re
import subprocess
import json
import logging
import sys

import requests

API_BASE = os.getenv("STA_API_BASE", "http://localhost:8000")
API_KEY = os.getenv("STA_API_KEY")

if not API_KEY:
    print("ERROR: STA_API_KEY environment variable is required.", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scout_loop")

TICKER_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

BULLISH_PATTERNS = [re.compile(r"\b" + w + r"\b") for w in ["buy", "bull", "bullish", "long", "calls", "moon"]]
BEARISH_PATTERNS = [re.compile(r"\b" + w + r"\b") for w in ["sell", "bear", "bearish", "short", "puts", "crash"]]


def get_active_tickers():
    """Fetch active tickers from the Markets Browser."""
    try:
        resp = requests.get(f"{API_BASE}/markets/kalshi/top", headers={"X-API-Key": API_KEY})
        resp.raise_for_status()
        markets = resp.json()
        return [m["ticker"] for m in markets[:5] if TICKER_PATTERN.match(m.get("ticker", ""))]
    except Exception as e:
        logger.error("Failed to fetch tickers: %s", e)
        return []


def scout_ticker(ticker):
    """Run opencli-rs to get sentiment for a ticker."""
    if not TICKER_PATTERN.match(ticker):
        logger.error("Invalid ticker format: %s", ticker)
        return None

    logger.info("Scouting sentiment for %s...", ticker)
    try:
        cmd = ["opencli-rs", "twitter", "search", "--query", ticker, "--format", "json", "--limit", "10"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error("opencli-rs failed: %s", result.stderr)
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.error("opencli-rs timed out for %s", ticker)
        return None
    except Exception as e:
        logger.error("Scout error for %s: %s", ticker, e)
        return None


def analyze_and_alert(ticker, tweets):
    """Correlate sentiment with opportunities using word-boundary matching."""
    if not tweets:
        return

    text = " ".join([str(t.get("text", "")).lower() for t in tweets])
    bullish = sum(len(p.findall(text)) for p in BULLISH_PATTERNS)
    bearish = sum(len(p.findall(text)) for p in BEARISH_PATTERNS)

    logger.info("%s Sentiment: Bullish=%d, Bearish=%d", ticker, bullish, bearish)

    if abs(bullish - bearish) > 3:
        logger.info("Sentiment Imbalance Detected for %s! Potential Alpha.", ticker)


def run_scout_cycle():
    tickers = get_active_tickers()
    if not tickers:
        logger.warning("No tickers found to scout.")
        return

    for t in tickers:
        tweets = scout_ticker(t)
        if tweets:
            analyze_and_alert(t, tweets)


if __name__ == "__main__":
    run_scout_cycle()
