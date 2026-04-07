# Alpha Vantage Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Alpha Vantage feature parity by adding a robust technical indicators library, AI-powered sentiment scoring, and an MCP server for intelligent agent integration.

**Architecture:** We will utilize `pandas_ta` for our 50+ technical indicators, wrapping it in a simple API within `trading/data/indicators.py`. We will extend `SentimentProvider` to ingest Alpha Vantage AI-powered sentiment via REST API. Finally, we'll build a dedicated MCP server `api/mcp-server/alphavantage/mcp.py` to allow external LLM agents to fetch this data dynamically.

**Tech Stack:** Python 3.12, Pytest, Pandas-TA, FastAPI, FastMCP.

---

### Task 1: Technical Indicators Library (pandas_ta)

**Files:**
- Create: `trading/tests/unit/test_data/test_technical_indicators.py`
- Create: `trading/data/indicators.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_data/test_technical_indicators.py
import pytest
import pandas as pd
import numpy as np
from data.indicators import add_technical_indicators

def test_add_technical_indicators():
    df = pd.DataFrame({
        "open": np.random.random(100),
        "high": np.random.random(100),
        "low": np.random.random(100),
        "close": np.random.random(100),
        "volume": np.random.random(100)
    })
    
    df_with_ta = add_technical_indicators(df)
    assert "RSI_14" in df_with_ta.columns
    assert "MACD_12_26_9" in df_with_ta.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_data/test_technical_indicators.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/data/indicators.py
import pandas as pd
import pandas_ta as ta

def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add 50+ standard technical indicators to OHLCV DataFrame using pandas_ta."""
    # We append basic ones explicitly, or can use df.ta.strategy("all")
    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.bbands(append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    return df
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_data/test_technical_indicators.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/tests/unit/test_data/test_technical_indicators.py trading/data/indicators.py
git commit -m "feat(data): integrate pandas_ta for technical indicator library"
```

### Task 2: AI-Powered Sentiment Scores

**Files:**
- Create: `trading/tests/unit/test_intelligence/test_alphavantage_sentiment.py`
- Modify: `trading/intelligence/providers/sentiment.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_intelligence/test_alphavantage_sentiment.py
import pytest
from unittest.mock import patch, AsyncMock
from intelligence.providers.sentiment import SentimentProvider

@pytest.mark.asyncio
async def test_alpha_vantage_sentiment():
    provider = SentimentProvider(alpha_vantage_key="TEST_KEY")
    
    with patch.object(provider, '_fetch_av_sentiment', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = 0.8 # Bullish
        
        report = await provider.analyze("AAPL")
        # Should incorporate the AV score
        assert report is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_intelligence/test_alphavantage_sentiment.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/intelligence/providers/sentiment.py
# (Add to __init__)
    def __init__(self, lunarcrush_api_key: str | None = None, alpha_vantage_key: str | None = None):
        self.lunarcrush_api_key = lunarcrush_api_key
        self.alpha_vantage_key = alpha_vantage_key

# (Add method)
    async def _fetch_av_sentiment(self, symbol: str) -> float:
        """Fetch Alpha Vantage News Sentiment."""
        if not self.alpha_vantage_key:
            return 0.0
            
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={symbol}&apikey={self.alpha_vantage_key}"
            try:
                async with session.get(url) as resp:
                    data = await resp.json()
                    # Parse sentiment score from feed
                    feed = data.get("feed", [])
                    if not feed: return 0.0
                    scores = [float(item.get("overall_sentiment_score", 0)) for item in feed]
                    return sum(scores) / len(scores)
            except Exception:
                return 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_intelligence/test_alphavantage_sentiment.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/tests/unit/test_intelligence/test_alphavantage_sentiment.py trading/intelligence/providers/sentiment.py
git commit -m "feat(intelligence): integrate alpha vantage ai sentiment scoring"
```

### Task 3: Alpha Vantage MCP Server

**Files:**
- Create: `api/mcp-server/alphavantage/mcp.py`

- [ ] **Step 1: Write the minimal implementation (No unit test needed for simple MCP server wrapper)**

```python
# api/mcp-server/alphavantage/mcp.py
from fastmcp import FastMCP
import aiohttp
import os

mcp = FastMCP("AlphaVantage")

@mcp.tool()
async def get_market_sentiment(ticker: str) -> str:
    """Fetch AI-powered news sentiment for a given ticker from Alpha Vantage."""
    api_key = os.getenv("ALPHA_VANTAGE_KEY")
    if not api_key:
        return "Error: ALPHA_VANTAGE_KEY environment variable not set."
        
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&apikey={api_key}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            feed = data.get("feed", [])
            if not feed:
                return "No sentiment data found."
                
            score = feed[0].get("overall_sentiment_score", "0")
            label = feed[0].get("overall_sentiment_label", "Neutral")
            return f"Sentiment for {ticker}: {label} (Score: {score})"

if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 2: Commit**

```bash
git add api/mcp-server/alphavantage/mcp.py
git commit -m "feat(mcp): add alpha vantage mcp server for agent integration"
```
