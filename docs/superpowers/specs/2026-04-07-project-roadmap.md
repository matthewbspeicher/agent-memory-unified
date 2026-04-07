# Project Roadmap — Agent Memory Unified Trading Engine

**Date:** 2026-04-07
**Author:** mspeicher + Claude

---

## Current State

- Bittensor Subnet 8 (Vanta Network) validator running on UID 144
- Trading engine with 15 strategy agents, SignalBus, paper trading mode
- **Market Intelligence Layer** (just shipped): 5 providers (on-chain, sentiment, anomaly, regime, risk audit) with circuit breakers, confidence enrichment, veto gate
- React dashboard with Bittensor status panel
- Backtesting framework (TaoshiBacktestEngine)
- Gemini contributions: quant-analyst agent, backtesting MCP, regime-aware memory

---

## Phase 0: Critical Updates (Do First)

### 0.1 Update Taoshi Validator to Vanta Network
- **Why:** PTN rebranded to Vanta Network. Repo moved to `github.com/taoshidev/vanta-network`. New deps required (`collateral_sdk`, `vanta-cli`). Scoring changed to softmax (top 10% miners get 56% of emissions = higher quality signals).
- **Action:** Clone new repo, install deps, update any PTN references in codebase
- **Docs:** `https://docs.taoshi.io/ptn/validator/installation/`

### 0.2 Upgrade Bittensor SDK to 10.2.0
- **Why:** Breaking changes in v10: `ExtrinsicResponse` return type, `Balance` type enforcement, `_ss58` param renames, CRv3 removed
- **Action:** Upgrade `trading/` from `bittensor>=10.0.0` to `bittensor>=10.2.0`. Audit `adapter.py`, `weight_setter.py` for ExtrinsicResponse handling
- **Keep:** `taoshi-ptn/` stays on `bittensor==9.12.1` (matches official validator requirements)
- **Migration guide:** `https://docs.learnbittensor.org/sdk/migration-guide`

### 0.3 Dev Tooling Quick Wins
```bash
# MCP servers (5 min each)
claude mcp add postgres -- npx -y @modelcontextprotocol/server-postgres "postgresql://postgres:secret@localhost:5432/agent_memory"
claude mcp add docker -- npx -y @modelcontextprotocol/server-docker

# Python tools
cd trading && source .venv/bin/activate
pip install pytest-xdist ty pre-commit ccxt pandas_ta quantstats
```

---

## Phase 1: Data & Connectivity (Week 1-2)

### 1.1 CCXT Exchange Integration
- **Why:** Fills `AnomalyProvider` stubs (volume, spread data). Unified API for 106+ exchanges.
- **Install:** `pip install ccxt`
- **Wire:** Create `trading/data/exchange_client.py` wrapping CCXT for real-time volume/spread/funding data
- **Feeds:** AnomalyProvider, future FundingRateArbAgent, future OrderFlowAgent

### 1.2 Funding Rate Data Source
- **Why:** Highest-signal alternative data. Funding rates predict short-term price moves.
- **Source:** Coinalyze free API (`api.coinalyze.net/v1/funding-rate`) or Binance direct
- **Action:** New `DerivativesDataProvider` or extend OnChainProvider with funding rate + OI signals

### 1.3 Historical Data Pipeline
- **Why:** Better backtesting with deeper history
- **Install:** `pip install binance-historical-data`
- **Action:** Download BTC/ETH 5m candles from `data.binance.vision`, store locally for backtest replay

### 1.4 LunarCrush Social Volume
- **Why:** Social volume spikes are leading indicators. Config slot already exists.
- **Action:** Wire `STA_INTEL_LUNARCRUSH_API_KEY` into SentimentProvider as secondary signal source

---

## Phase 2: New Alpha Sources (Week 2-4)

### 2.1 Funding Rate Arbitrage Agent
- **Expected:** ~19% annual returns, <2% max drawdown (research-backed)
- **Strategy:** Spot long + perpetual short when funding is positive. Delta-neutral.
- **Implementation:** New `FundingRateArbAgent(StructuredAgent)` monitoring rates via CCXT, executing hedged positions
- **Priority:** Highest-conviction new alpha source

### 2.2 Order Flow / CVD Signal
- **Why:** Most predictive single feature per 2026 research. +15% improvement in reversal prediction vs RSI alone.
- **Implementation:** Subscribe to exchange WebSocket trade streams, compute Cumulative Volume Delta, feed CVD divergence as confirmation into BittensorSignalAgent and MultiFactorAgent
- **Integration:** New `OrderFlowProvider` in intelligence layer, or direct signal into agents

### 2.3 HMM Regime Detection Upgrade
- **Why:** Current heuristic thresholds are fragile. HMM captures regime transitions probabilistically.
- **Install:** `pip install hmmlearn`
- **Action:** Replace `RegimeMemoryManager.detect_regime()` with 3-4 state HMM (trending_bull, trending_bear, volatile, quiet). Use regime state to gate which agents are active and their ensemble weight.
- **Paper:** "Markov and HMMs for Regime Detection in Crypto" (Preprints.org, Mar 2026)

### 2.4 XGBoost Meta-Learner for Signal Combination
- **Why:** Captures non-linear signal interactions that linear Kelly/Sharpe weighting misses.
- **Install:** `pip install xgboost`
- **Action:** Replace (or complement) EnsembleOptimizer's linear weights with XGBoost trained on agent signals. Walk-forward calibration: 30-day window, daily rebalance.

---

## Phase 3: Risk & Execution (Week 4-6)

### 3.1 Volatility Targeting Position Sizing
- **Formula:** `position_size = target_risk / realized_vol_20d`
- **Action:** Insert between signal generation and order submission. Adapts to market conditions automatically.
- **Pairs with:** Regime detection (reduce risk in volatile regimes)

### 3.2 Portfolio Risk Management
- **Install:** `pip install riskfolio-lib pyportfolioopt`
- **Action:** Formal CVaR/risk parity optimization across 15 agents. Replace ad-hoc position sizing.

### 3.3 Walk-Forward Backtesting
- **Why:** Current 7-day lookback in EnsembleOptimizer is too short for stable estimates
- **Action:** Implement 30-day calibration window with daily rebalance. Add look-ahead bias checks on Bittensor signal timestamps. Model 0.04-0.1% per side + slippage.
- **Install:** `pip install vectorbt` for rapid parameter sweeps

### 3.4 SAC Reinforcement Learning for Dynamic Sizing
- **Install:** `pip install stable-baselines3`
- **State:** (regime, signal vector, portfolio state)
- **Action:** Position sizes for each signal
- **Reward:** Risk-adjusted return (Sharpe)
- **Reference:** FinRL_Crypto (`github.com/AI4Finance-Foundation/FinRL_Crypto`)

---

## Phase 4: Observability & Infrastructure (Ongoing)

### 4.1 Prometheus Metrics
```bash
pip install prometheus-fastapi-instrumentator
```
- Auto `/metrics` endpoint for request latency, throughput, error rates
- Add custom metrics for: signals processed, enrichments applied, vetos issued, provider latency

### 4.2 Grafana Dashboard
- Add `prometheus` + `grafana` services to `docker-compose.yml`
- Build dashboards for: trading engine health, intelligence layer performance, miner signal quality

### 4.3 Sentry Error Tracking
```bash
pip install sentry-sdk[fastapi,opentelemetry]
```
- Wire into FastAPI app, connect OTel traces

### 4.4 Structured Logging Upgrade
```bash
pip install structlog asgi-correlation-id
```
- Replace custom `JSONFormatter` with structlog for automatic trace ID injection, correlation IDs

### 4.5 CI Enhancements
- `pytest-xdist` (`-n auto`) for parallel test execution
- `codecov/codecov-action@v5` for coverage reporting
- `ty check .` type checking job (advisory)
- Weekly `mutmut` mutation testing cron

---

## Phase 5: Multi-Subnet Expansion (Month 2+)

### 5.1 SN28 (S&P 500 Oracle) Integration
- Equity index predictions from Bittensor miners
- Query SN28 validators via dendrite, pipe into SignalBus alongside SN8 signals
- Enables equity-crypto correlation signals

### 5.2 SN15 (BitQuant) Integration
- REST API at `bitquant.io` for AI-driven crypto analysis
- Augment technical analysis agents with on-demand quant insights

### 5.3 dTAO Alpha Token Strategy
- Monitor Vanta Alpha token economics
- Validator rewards now depend on market demand for Alpha tokens
- Consider staking strategy to boost consensus power

---

## Phase 6: ML Pipeline (Month 2-3)

### 6.1 Lightweight TFT/N-BEATS Forecast
- **Install:** `pip install pytorch-forecasting`
- Train on 5m BTC/ETH with Bittensor signals + CVD + funding rates + on-chain flows
- Directional forecast as one more agent in ensemble
- **Reference:** "Adaptive TFTs for Cryptocurrency Prediction" (arxiv 2509.10542)

### 6.2 CryptoBERT Sentiment
- Fine-tuned crypto sentiment extraction from news/social
- Feed as one feature into ensemble (not for trading decisions directly)
- LLMs for sentiment extraction, not trading: GPT-5 lost 60%+ in Alpha Arena live trading

### 6.3 Automated Feature Importance
- Use TFT's attention mechanism to identify which features matter
- Prune low-value signals, amplify high-value ones
- Continuous feedback loop

---

## Key Libraries to Install

### Immediate
```bash
pip install ccxt pandas_ta quantstats pytest-xdist ty pre-commit
```

### Phase 2
```bash
pip install hmmlearn xgboost lightgbm binance-historical-data
```

### Phase 3
```bash
pip install vectorbt riskfolio-lib pyportfolioopt stable-baselines3
```

### Phase 4
```bash
pip install prometheus-fastapi-instrumentator structlog asgi-correlation-id sentry-sdk[fastapi,opentelemetry]
```

### Phase 6
```bash
pip install pytorch-forecasting
```

---

## Key Papers

| Paper | arxiv/Source | Key Finding |
|-------|-------------|-------------|
| Orchestration Framework for Financial Agents | 2512.02227 | Multi-agent arch, 8.4% BTC return in 17 days |
| Increase Alpha | 2509.16707 | Feature engineering > model complexity, Sharpe 2.54 |
| Order Flow and Crypto Returns | J. Int. Financial Markets, Jan 2026 | Order flow dominates for prediction |
| HMMs for Regime Detection in Crypto | Preprints.org, Mar 2026 | Validates HMM on BTC 2024-2026 |
| Crypto Portfolio: SAC and DDPG | 2511.20678 | SAC nearly tripled investment |
| Adaptive TFTs for Crypto | 2509.10542 | Regime-adaptive transformer prediction |

---

## Monitoring Resources

| Tool | URL | Purpose |
|------|-----|---------|
| Taoshi Dashboard | dashboard.taoshi.io | Miner/validator performance |
| Taostats | taostats.io/validators | Validator analytics, staking |
| Subnet Alpha | subnetalpha.ai/subnet/vanta/ | Vanta-specific analytics |
| TaoMarketCap | taomarketcap.com | Subnet tracking |
| wandb | wandb.ai | KPI/metrics logging |
