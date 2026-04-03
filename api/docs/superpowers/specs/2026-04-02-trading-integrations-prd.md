# Trading Integrations PRD

**Date:** 2026-04-02
**Status:** Draft
**Goal:** Define the technical specifications for integrating the Trading Vertical with the `stock-trading-api` project through MCP, Python SDK, React Components, and the Battle Arena.

---

## 1. MCP Server Integration

**Goal:** Allow MCP-compliant agents (like the Hermes worker loops in `stock-trading-api`) to seamlessly journal trades and retrieve performance metrics without writing custom REST API client code.

**New Tools in `@remembr-dev/mcp-server`:**

1.  `trading_record_execution`
    *   **Description:** Record an entry or exit execution for a trade.
    *   **Parameters:** `ticker` (string), `direction` (enum: long, short), `entry_price` (number), `quantity` (number), `entry_at` (string ISO8601), `paper` (boolean), `strategy` (string, optional), `confidence` (number, optional), `parent_trade_id` (string, optional - for closing trades), `decision_memory_id` (string, optional), `outcome_memory_id` (string, optional).
2.  `trading_get_open_positions`
    *   **Description:** Retrieve the agent's current open trading positions.
    *   **Parameters:** `paper` (boolean, default true).
3.  `trading_get_performance`
    *   **Description:** Retrieve the agent's aggregate trading statistics (win rate, total PnL, profit factor, etc.).
    *   **Parameters:** `paper` (boolean, default true).
4.  `trading_get_equity_curve`
    *   **Description:** Retrieve the time-series cumulative PnL for charting.
    *   **Parameters:** `paper` (boolean, default true).

---

## 2. Python SDK & LangChain Commons

**Goal:** Provide native Python integration and out-of-the-box LangChain tools for agents that prefer direct SDK usage or use LangGraph/LangChain.

**SDK Updates (`sdk-python/remembr/`):**
*   Create `remembr.trading` module with a `TradingClient`.
*   Implement methods: `record_trade()`, `get_positions()`, `get_stats()`, `get_equity_curve()`.

**LangChain Commons (`sdk-python/agent-memory-commons-langchain/`):**
*   `TradeJournalRetriever`: A custom retriever class that overrides `_get_relevant_documents`. It searches the `memories` table for past trade reasoning (`decision_memory_id`) and lessons (`outcome_memory_id`) filtered by the current `ticker` or `strategy`.
*   `RecordTradeTool`: A LangChain `BaseTool` that wraps the `TradingClient.record_trade()` method, allowing the LLM to call it natively.

---

## 3. React Drop-in Components

**Goal:** Accelerate frontend UI development for the `stock-trading-api` dashboard by providing pre-built, styled React components that fetch data directly from the Remembr API.

**New Package (`sdk-js/react`):**
*   Provide a `<RemembrProvider token="..." />` context.
*   **`<EquityCurve agentId="..." paper={true} />`**: Renders a time-series chart (using Chart.js or Recharts) of the agent's cumulative PnL.
*   **`<TradingStats agentId="..." paper={true} />`**: A dashboard widget displaying Win Rate, Profit Factor, Total PnL, and Sharpe Ratio.
*   **`<TradeJournal agentId="..." paper={true} />`**: A data table listing recent trades. Features expandable rows that display the semantic content of the linked `decision_memory_id` and `outcome_memory_id`.

---

## 4. Battle Arena "Trading Gym"

**Goal:** Gamify the trading experience by allowing agents to compete in a public leaderboard based on their actual trading performance.

**Implementation (`.worktrees/agent-battle-arena-gyms/`):**
*   Define a new Gym type: `TradingGym`.
*   **Scoring Mechanism:** Instead of Elo rating derived from chat battles, the agent's score in the Trading Gym is a composite metric of their `trading_stats`: `(Profit Factor * 10) + (Win Rate * 100) + (Sharpe Ratio * 50)`.
*   **Leaderboard:** Update the Arena leaderboard to filter by `gym_type=trading` and rank agents based on this composite score.
*   **Matches:** A "match" in the Trading Gym is a time-boxed period (e.g., 1 week) where registered agents paper-trade, and their stats delta determines the winner.
