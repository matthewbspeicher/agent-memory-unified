# Research: TradingView MCP Jackson Integration

## 1. Overview of `tradingview-mcp-jackson`
The repository `LewisWJackson/tradingview-mcp-jackson` is an improved fork of a Model Context Protocol (MCP) server that connects LLM agents to a locally running TradingView Desktop app via the Chrome DevTools Protocol (CDP).

### Key Features & Capabilities
*   **Granular Tooling**: It exposes 81 specific tools to the LLM (e.g., `quote_get`, `chart_set_timeframe`, `data_get_pine_lines`) rather than one massive "read chart" tool. This preserves the context window and forces the agent to explicitly ask for what it needs.
*   **The "Morning Brief" Workflow**: A defining feature where the agent iterates over a user-defined watchlist, extracts indicator values, applies bias/risk criteria defined in a static `rules.json` file, and returns a structured session bias.
*   **Session Persistence**: Daily briefs are saved locally so the agent can compare today's bias against yesterday's, effectively serving as short-term memory.
*   **Raw Data Transparency**: It does not pre-interpret data. It streams raw indicator values and Pine Script drawings (lines, boxes, tables) to the agent, forcing the agent to reason about them in its own trace.

---

## 2. Key Learnings for `agent-memory-unified`

### A. Rule-Driven Agent Alignment
The Jackson fork separates execution logic from user criteria by using a static `rules.json` (watchlist, bias criteria, risk rules). In our Python trading bot, we can implement a similar `trading_rules.yaml` that our Consensus/Router agents parse. This provides a clear boundary between "how the AI analyzes" and "what the user's risk tolerance is."

### B. Context Window Preservation (Granularity)
The Jackson fork solves context constraints (like massive OHLCV payloads or 200KB Pine Scripts) by offering `summary: true` flags and highly targeted tools. In our Python bot (`trading/agents/`), we should audit our data tools (e.g., `get_market_data`) to ensure we are offering granular sub-tools rather than returning monolithic JSON blobs that exhaust the context window.

### C. Proactive "Pre-Session" Memory (The Morning Brief)
Our platform features a shared Memory API (Laravel). The "Morning Brief" concept is perfectly aligned with this. Instead of agents only reacting to signals, we can schedule a "Morning Briefing" routine where the agents analyze the broad market state, summarize the session bias, and push this as a global "Memory" to the Laravel API. All subsequent trade decisions that day will inject this Morning Brief memory to align with the daily bias.

---

## 3. Incorporation Plan

To incorporate the concepts from this repo into our platform, we propose the following actionable phases:

### Phase 1: Implement the "Morning Brief" Memory Workflow
1.  Create a scheduled job in the Python trading bot (`trading/brief/` or `trading/warroom/`) that runs before the primary market session.
2.  The job will evaluate a configured watchlist against a `risk.yaml` / `trading_rules.yaml` file.
3.  The LLM will generate a structured "Session Bias" report.
4.  This report will be sent to the **Laravel Memory API** as a high-priority, daily memory entity, accessible by the frontend React dashboard and all trading agents.

### Phase 2: Refactor Agent Tooling for Granularity
1.  Audit the tools exposed to our `Router` and `Consensus` agents in Python.
2.  Break down large data retrieval tools into specific MCP-style granular functions (e.g., `get_current_price`, `get_recent_volatility_summary`, `get_key_levels`).
3.  Introduce a `summary=True` pattern for historical data fetches to reduce token usage and improve reasoning speed.

### Phase 3: (Optional) The BYO-TradingView Companion
Since `tradingview-mcp-jackson` relies on a local TradingView Desktop app, it cannot run natively on our cloud servers. However, we could:
1.  Provide a standalone Node.js "Companion App" based on this repo.
2.  Users run the companion locally on their desktop.
3.  The companion streams their live TradingView chart state (lines, drawn levels, current visible timeframe) up to our Laravel API via WebSockets/Redis Streams.
4.  Our cloud agents can then use the user's actual TradingView chart as visual context when scoring signals!