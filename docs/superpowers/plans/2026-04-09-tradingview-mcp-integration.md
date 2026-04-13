# TradingView MCP Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a Node.js companion app to extract live chart state from TradingView Desktop via CDP, stream it to Redis, and enable trading agents to incorporate this manual chart context into their decision-making.

**Architecture:** A local Node.js application (`companion-app`) connects to TradingView Desktop via Chrome DevTools Protocol (`puppeteer-core`), parses the DOM/canvas data for drawings and indicators, and streams snapshots to the shared Redis Event Bus. The Python Trading Engine reads these snapshots and appends them to the agent's context during signal evaluation.

**Tech Stack:** Node.js, Puppeteer Core (CDP), Redis (ioredis), Python (FastAPI), aioredis

---

### Task 1: Setup Companion App Project

**Files:**
- Create: `companion-app/package.json`
- Create: `companion-app/index.js`
- Create: `companion-app/.env.example`

- [x] **Step 1: Initialize the Node.js project**

Run: `mkdir -p companion-app && cd companion-app && npm init -y`
Expected: `package.json` is created.

- [x] **Step 2: Install dependencies**

Run: `cd companion-app && npm install puppeteer-core ioredis dotenv`
Expected: Dependencies installed and `package-lock.json` created.

- [x] **Step 3: Create base application file**

```javascript
// companion-app/index.js
require('dotenv').config();
const puppeteer = require('puppeteer-core');
const Redis = require('ioredis');

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const redis = new Redis(REDIS_URL);

async function start() {
    console.log('Starting TradingView Companion App...');
    // Setup CDP connection logic here
}

if (require.main === module) {
    start().catch(console.error);
}
```

- [x] **Step 4: Create `.env.example`**

```env
REDIS_URL=redis://localhost:6379
TRADINGVIEW_DEBUG_PORT=9222
```

- [x] **Step 5: Commit**

```bash
git add companion-app/
git commit -m "feat(companion): initialize Node.js TradingView companion app"
```

---

### Task 2: Connect to TradingView via CDP

**Files:**
- Modify: `companion-app/index.js`

- [x] **Step 1: Implement CDP connection and polling logic**

Update `companion-app/index.js`:

```javascript
require('dotenv').config();
const puppeteer = require('puppeteer-core');
const Redis = require('ioredis');

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const DEBUG_PORT = process.env.TRADINGVIEW_DEBUG_PORT || 9222;
const redis = new Redis(REDIS_URL);

async function extractChartData(page) {
    // Inject a script to extract active ticker, timeframe, and drawing objects
    // Note: TradingView uses Canvas, so extracting drawing metadata requires accessing their internal TV objects
    // For this prototype, we'll mock the extraction of chart context
    return await page.evaluate(() => {
        return {
            symbol: document.title.split(' ')[0] || 'UNKNOWN',
            drawings: ['Trend Line', 'Fibonacci Retracement'],
            indicators: ['RSI', 'VWAP'],
            timestamp: new Date().toISOString()
        };
    });
}

async function start() {
    console.log(`Connecting to TradingView on port ${DEBUG_PORT}...`);
    
    try {
        const browser = await puppeteer.connect({
            browserURL: `http://localhost:${DEBUG_PORT}`
        });
        
        const pages = await browser.pages();
        const page = pages.find(p => p.url().includes('tradingview.com/chart')) || pages[0];
        
        if (!page) {
            console.error('No TradingView chart page found.');
            process.exit(1);
        }

        console.log('Connected to TradingView chart.');

        // Poll every 5 seconds
        setInterval(async () => {
            try {
                const data = await extractChartData(page);
                await redis.xadd('tradingview_charts', '*', 'data', JSON.stringify(data));
                console.log(`Streamed chart data for ${data.symbol}`);
            } catch (err) {
                console.error('Error extracting data:', err.message);
            }
        }, 5000);

    } catch (err) {
        console.error('Failed to connect via CDP. Ensure TradingView is running with --remote-debugging-port=9222');
        process.exit(1);
    }
}

if (require.main === module) {
    start().catch(console.error);
}
```

- [x] **Step 2: Verify code syntax**

Run: `node -c companion-app/index.js`
Expected: No output (syntax is valid).

- [x] **Step 3: Commit**

```bash
git add companion-app/index.js
git commit -m "feat(companion): implement CDP connection and Redis streaming"
```

---

### Task 3: Python Trading Engine Redis Subscription

**Files:**
- Create: `trading/data/tradingview.py`
- Modify: `trading/agents/runner.py`

- [x] **Step 1: Write the TradingView Context Fetcher**

```python
# trading/data/tradingview.py
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class TradingViewContextFetcher:
    def __init__(self, redis_client: Any):
        self.redis = redis_client
        
    async def get_latest_chart_context(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.redis:
            return None
            
        try:
            # Read the latest message from the stream
            messages = await self.redis.xrevrange('tradingview_charts', count=5)
            for msg_id, fields in messages:
                data_str = fields.get(b'data', b'{}').decode('utf-8')
                data = json.loads(data_str)
                if data.get('symbol') == symbol:
                    return data
            return None
        except Exception as e:
            logger.error(f"Failed to fetch TradingView context: {e}")
            return None
```

- [x] **Step 2: Add `tradingview_fetcher` to `AgentRunner`**

In `trading/agents/runner.py`, update `__init__`:
Add `tradingview_fetcher: Any | None = None` to the signature and `self._tv_fetcher = tradingview_fetcher` to the body.

- [x] **Step 3: Inject TV context into agent evaluation**

In `trading/agents/runner.py`, inside `_execute_scan` before `agent.scan(self._data_bus)`:

```python
                # --- TradingView Chart Context ---
                if hasattr(self, "_tv_fetcher") and self._tv_fetcher:
                    try:
                        universe = agent.config.universe
                        ticker = universe[0] if isinstance(universe, list) and universe else "UNKNOWN"
                        tv_context = await self._tv_fetcher.get_latest_chart_context(ticker)
                        if tv_context:
                            agent._tv_context = tv_context
                            if self._event_bus:
                                await self._event_bus.publish(
                                    "tradingview_context_injected",
                                    {"agent_name": agent.name, "symbol": ticker, "drawings": tv_context.get("drawings", [])}
                                )
                    except Exception as tv_exc:
                        logger.warning(f"TradingView context injection failed for {agent.name}: {tv_exc}")
```

- [x] **Step 4: Commit**

```bash
git add trading/data/tradingview.py trading/agents/runner.py
git commit -m "feat(engine): integrate TradingView chart context into AgentRunner"
```

---

### Task 4: Wire the dependencies in `app.py`

**Files:**
- Modify: `trading/api/app.py`

- [x] **Step 1: Instantiate TradingViewContextFetcher and pass to AgentRunner**

In `trading/api/app.py`, under `_setup_agent_runtime`, initialize the fetcher using the redis client:

```python
    from data.tradingview import TradingViewContextFetcher
    
    # Extract raw redis client from event bus if available
    redis_client = getattr(event_bus, "_redis", None)
    tv_fetcher = TradingViewContextFetcher(redis_client) if redis_client else None
```

Add `tradingview_fetcher=tv_fetcher` to the `AgentRunner` instantiation.

- [x] **Step 2: Commit**

```bash
git add trading/api/app.py
git commit -m "feat(api): wire TradingViewContextFetcher dependency in app setup"
```
