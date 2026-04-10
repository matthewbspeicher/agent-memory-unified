# Design Spec: TradingView MCP & Memory Loop Integration

**Date:** 2026-04-09
**Status:** Draft
**Topic:** Incorporating TradingView MCP patterns and Unified Memory into the Trading Bot.

## 1. Executive Summary
This design integrates key patterns from the `jackson-video-resources/claude-tradingview-mcp-trading` repository and the `tradesdontlie/tradingview-mcp` project into the `agent-memory-unified` monorepo. It bridges local TradingView analysis with cloud-based autonomous agents and ensures session-level alignment via the Laravel Memory API.

## 2. Components & Architecture

### A. Local-to-Cloud Bridge (The Companion App)
*   **Source:** Fork of `tradesdontlie/tradingview-mcp`.
*   **Role:** Extracts live chart state (drawings, indicators, timeframe) via CDP from TradingView Desktop.
*   **Transmission:** Streams JSON snapshots to the platform's Redis Event Bus.
*   **Key Path:** `companion-app/` (Node.js).

### B. Safety-First Scalping Logic (Snap-Back)
*   **Strategy:** `trading/strategies/snapback_scalper.py`.
*   **Indicators:** RSI(3), VWAP, EMA(8).
*   **Rules Engine Update:**
    *   Add `volatility_above` condition (BB Width check).
    *   Add `DistanceToVWAPRule` (1.5% gate).
*   **Config:** Managed via `trading/trading_rules.yaml`.

### C. Persistent Memory Loop (Living Brief)
*   **Workflow:** `trading/brief/session_bias.py`.
*   **Integration:**
    1.  Generator POSTs daily bias to **Remembr.dev** via `TradingMemoryClient.store_shared()` (`market_regime` type).
    2.  `OpportunityRouter` retrieves bias memory during signal evaluation via `AgentRunner` context injection.
    3.  **Contradiction Logic:** If `signal.direction != session_bias.direction`, apply a `CalibrationRecommendation.multiplier` (default 0.8x) or block if `risk_overlay.require_bias_alignment` is true.
*   **Frontend:** `frontend/src/components/trading/SessionBiasCard.tsx` (New component).

## 3. Data Flow
1.  **Morning:** `SessionBiasGenerator` scans market -> generates report -> saves to **Remembr.dev**.
2.  **Live:** `Companion App` scans TV Desktop -> streams chart context to Redis.
3.  **Execution:** `OpportunityRouter` receives signal -> fetches Memory Bias + Redis Chart Context -> applies Snap-Back rules (including new `volatility_above` BB Width check) -> Executes/Blocks.

## 4. Success Criteria
*   Local TradingView drawings are visible in Agent reasoning traces.
*   Agents successfully block "chasing" trades (>1.5% from VWAP).
*   Daily bias is visible on the React Dashboard.
*   Trade logs show "Bias Alignment" as a scoring factor.

## 5. Risk & Mitigations
*   **Redis Latency:** Polling/Streaming from local must be debounced to prevent Redis bloat.
*   **Auth:** Companion app requires `STA_REDIS_PASSWORD` and `STA_MEMORY_API_KEY`.
