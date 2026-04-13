# Design Spec: Agent Studio (Forge & Lab)

**Status:** Proposed
**Date:** 2026-04-13
**Track:** Agent Lifecycle & Evaluation
**Complexity:** High
**Goal:** Provide a unified UI to create (Forge), validate (Lab), and deploy autonomous trading/arena agents.

---

## 1. Executive Summary
The Agent Studio unifies the creation and evaluation of AI agents. Users can draft new personas, define their system prompts, and configure their hyperparameters in the **Forge**. Before deployment, these agents are evaluated in the **Lab**, which runs a synchronous backtest against historical market data (or simulated arena environments). Only agents that pass performance thresholds are "Deployed" to the live roster.

---

## 2. Architecture & Data Model

### 2.1 The Draft System
To prevent incomplete or untested agents from participating in live markets/arenas, the Studio uses a "Draft" data model.
- **Backend:** A new `identity.agent_drafts` table in PostgreSQL.
- **Fields:** `id`, `name`, `system_prompt`, `model`, `hyperparameters` (JSONB), `status` (draft, tested, deployed), `backtest_results` (JSONB).
- **Flow:** 
    1. Forge UI -> POST `/v1/agents/drafts` -> Returns Draft ID.
    2. Lab UI -> POST `/v1/agents/drafts/{id}/backtest` -> Runs synchronous simulation -> Updates `backtest_results`.
    3. Lab UI -> POST `/v1/agents/drafts/{id}/deploy` -> Promotes draft to `identity.agents` and generates a live `amu_` token.

### 2.2 The Hybrid Backtesting Engine
The backtesting engine (`scripts/backtest_system.py`) is refactored into a core module (`trading/evaluation/engine.py`) exposed via a FastAPI endpoint.
- **Synchronous Execution:** The `/backtest` endpoint blocks until the simulation completes. For UI responsiveness, tests are capped at a set timeframe (e.g., 30 days of 1H candles).
- **Hybrid Metrics:**
    - *Trading:* Evaluates the agent's signal generation against historical OHLCV data. Returns Sharpe Ratio, Win Rate, Max Drawdown, and an Equity Curve array.
    - *Esports/Arena:* Simulates the agent in 100 iterations of the Werewolf or Cybersecurity engine against baseline dummy agents. Returns Win Rate, Elo Delta, and Deception Rate.

---

## 3. Frontend Integration (React 19)

### 3.1 The Forge (Creation UI)
- **Path:** `/studio/forge`
- **Components:** 
    - `AgentBuilderForm`: Inputs for Name, Avatar/Class, and System Prompt.
    - `HyperparameterTuner`: Sliders for Temperature, Risk Tolerance, and Top-P.
    - `DraftList`: A sidebar showing saved but undeployed agent drafts.

### 3.2 The Lab (Evaluation UI)
- **Path:** `/studio/lab/{draft_id}`
- **Components:**
    - `BacktestConfigurator`: Select simulation type (Trading vs Arena) and timeframe.
    - `PerformanceDashboard`: Displays the Equity Curve chart (using Recharts or lightweight-charts) and metric cards (Sharpe, ROI).
    - `DeployGate`: A button that is disabled until a backtest is run and yields a positive ROI/Win Rate.

---

## 4. Success Criteria
- [ ] Users can create and save an agent draft without generating a live authentication token.
- [ ] The FastAPI backend successfully executes a hybrid backtest within 5 seconds and returns structured JSON metrics.
- [ ] The React frontend renders the backtest equity curve and unlocks the "Deploy" button upon success.
- [ ] Clicking "Deploy" moves the draft to the live `agents` table and provisions a usable API token.
