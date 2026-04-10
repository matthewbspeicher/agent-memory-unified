# Bring Agents to Life: Arena, Gym, Backtesting & Arbitrage

## ✅ COMPLETION STATUS

**All 23 tasks COMPLETE** — 2026-04-09

```
Wave 1 Arena Core (7/7): ✅ COMPLETE
Wave 2 Parameter Optimization (5/5): ✅ COMPLETE
Wave 3 Self-Reflection + Stress Tests (6/6): ✅ COMPLETE
Wave 4 Multi-Agent Integration (5/5): ✅ COMPLETE
```

**Key files created/modified:**
- `trading/tournament/engine.py` — TournamentEngine with ELO, run_tournament, run_arena_gym_cycle
- `trading/tournament/store.py` — TournamentStore with ELO storage
- `trading/agents/tuning.py` — AdaptiveTuner with grid_search, genetic_optimize, monte_carlo
- `trading/gym/reflection.py` — SelfReflectionAgent + TradeAnalyzer
- `trading/gym/stress_tests/` — scenarios.py, injector.py
- `trading/api/routes/ws.py` — Added /spreads WebSocket endpoint
- `trading/strategies/dsl.py` — Added ArbitrageDSLAgent
- `trading/api/routes/tournament.py` — Tournament API endpoints
- `trading/api/routes/tuning.py` — Tuning API endpoints

---

## TL;DR

> **Quick Summary**: Build a unified trading platform where 13+ agents compete in a capital tournament (Arena), train via parameter optimization + self-reflection (Gym), with enhanced backtesting and arbitrage execution.
> 
> **Deliverables**:
> - Arena: Competitive agent evaluation with daily backtest-based ranking, ELO ratings, auto-promotion
> - Gym: Full training loop with parameter tuning + LLM self-reflection + stress test scenarios
> - Backtesting: Multi-agent backtest, parameter sweep, walk-forward validation
> - Arbitrage: Full dual-leg execution wiring with real-time spread monitoring
> - Knowledge Graph: Historical tracking of tournament results, agent insights, and regime-aware patterns
> 
> **Estimated Effort**: XL (multiple sprints)
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Arena Core → Tournament Wiring → Gym Core → Parameter Optimization → Full Integration

---

## Context

### Original Request
User wants to "bring agents to life" - make the 13 active trading agents come alive through:
1. **Arena** - Capital Tournament where agents compete for allocation
2. **Gym** - Full training loop (parameter tuning + self-reflection)
3. **Backtesting** - Enhanced backtest infrastructure
4. **Arbitrage** - Full execution wiring

### Research Findings

**What's Built:**
- 30 strategy implementations
- 13 active agents in agents.yaml
- Basic BacktestEngine in data/backtest.py
- AdaptiveTuner for basic parameter adjustment
- Capital Governor in risk engine
- Tournament config in learning.yaml (Sharpe stages: 1.5 → 1.8 → 2.0)
- 5 arbitrage strategies (Kalshi, Polymarket, Funding Rate)
- SpreadStore and API routes for arbitrage
- TradingKnowledgeGraph with temporal entity-relationship tracking

**What's Missing:**
- Arena class for competitive evaluation
- Tournament brackets with auto-promotion
- ELO rating system (mentioned but not wired)
- Parameter sweep/optimization (beyond basic grid)
- Self-reflection LLM loop
- Stress test scenarios
- Multi-agent backtest capability
- Full dual-leg arbitrage execution

### User Decisions
- Arena: Historical backtest-based, daily promotion
- Gym: Full training loop (parameter tuning + self-reflection)
- Arbitrage: Full execution wiring

---

## Work Objectives

### Core Objective
Transform 13 passive trading agents into an active, competitive ecosystem where:
1. Agents compete in daily backtest tournaments
2. Top performers earn capital allocation
3. Agents learn from their trades via parameter tuning + self-reflection
4. Arbitrage opportunities are automatically detected and executed
5. All outcomes are tracked in the Knowledge Graph for historical pattern discovery and regime-aware decision making

### Concrete Deliverables
- Arena class with tournament orchestration
- ELO rating integration with consensus.py
- Daily backtest ranking system
- Stage promotion/demotion workflow
- Enhanced parameter optimizer (grid + genetic)
- LLM self-reflection pipeline
- Stress test scenario injector
- Multi-agent backtest capability
- Full dual-leg arbitrage execution

### Definition of Done
- [ ] Arena runs daily backtest tournament for all agents
- [ ] Agents ranked by Sharpe/max_drawdown/win_rate
- [ ] Top agents auto-promoted per learning.yaml stages
- [ ] Gym produces optimized parameters for each agent
- [ ] Self-reflection generates actionable insights
- [ ] Multi-agent backtest validates consensus/ensemble
- [ ] Arbitrage executes dual-leg trades automatically

### Must Have
- Daily automated tournament evaluation
- ELO-based agent rankings
- Parameter optimization framework
- Self-reflection via LLM
- Full arbitrage execution pipeline

### Must NOT Have
- UI components (dashboard is out of scope)
- New broker integrations
- Real money trading automation
- Modifications to existing strategy logic

---

## Verification Strategy

### Test Infrastructure
- Framework: pytest
- Unit tests: trading/tests/unit/
- Integration tests: trading/tests/integration/
- Test commands: `cd trading && make test`

### QA Policy
Every task includes Agent-Executed QA Scenarios:
- Arena: Run tournament, verify rankings match expected
- Gym: Run optimization, verify parameters improve backtest
- Backtest: Run multi-agent, verify consensus output
- Arbitrage: Submit spread, verify dual-leg execution

---

## Execution Strategy

### Wave 1 (Foundation - Arena Core + Arbitrage Execution)
```
├── Task 1: Arena class with tournament orchestration
├── Task 2: Backtest ranking engine (Sharpe, max_drawdown, win_rate)
├── Task 3: ELO rating integration with consensus.py
├── Task 4: Stage promotion/demotion workflow
├── Task 5: Arbitrage spread store with claim semantics
├── Task 6: Dual-leg execution engine
└── Task 7: Daily tournament cron job
```

### Wave 2 (Gym Core - Parameter Tuning)
```
├── Task 8: Enhanced AdaptiveTuner with grid search
├── Task 9: Genetic algorithm parameter optimizer
├── Task 10: Parameter sweep API endpoint
├── Task 11: Walk-forward validation enhancement
└── Task 12: Monte Carlo simulation for confidence intervals
```

### Wave 3 (Gym Advanced - Self-Reflection + Stress Tests)
```
├── Task 13: LLM self-reflection pipeline
├── Task 14: Trade outcome analysis agent
├── Task 15: Stress test scenario injector
├── Task 16: Flash crash scenario
├── Task 17: Volatility spike scenario
└── Task 18: Gap open scenario
```

### Wave 4 (Integration - Multi-Agent + Full Wiring)
```
├── Task 19: Multi-agent backtest capability
├── Task 20: Consensus voting backtest simulation
├── Task 21: Arena-Gym integration (optimize → compete → learn)
├── Task 22: Real-time spread monitoring
└── Task 23: Unified arbitrage DSL
```

---

## TODOs

### Wave 1 (Foundation - Arena Core + Arbitrage Execution)

- [x] 1. **Arena class with tournament orchestration** ✅ COMPLETE

  **What to do**:
  - **ENHANCE existing** `trading/tournament/engine.py` TournamentEngine (already has evaluate_all, promote, demote, AI gate)
  - Add ELO update method that writes to `consensus.py` AgentWeightProfile
  - Add KG integration for tournament results
  - Methods to add: `update_elo_ratings()`, `store_to_kg()`
  - Use existing hourly cron from `learning.yaml:30` (`0 * * * *`)
  - **KG Integration**: Store tournament results to TradingKnowledgeGraph for historical tracking

  **Acceptance Criteria**:
  - [ ] TournamentEngine.evaluate_all() runs without errors
  - [ ] ELO updates written to consensus.py AgentWeightProfile after each evaluation
  - [ ] Tournament results persisted to KG (triples: agent-ran_tournament-date, agent-scored_sharpe-N, agent-ranked_N)

  **References**:
  - `trading/agents.yaml` - Agent configuration (13 active agents)
  - `trading/agents/runner.py` - AgentRunner for running agents
  - `trading/tournament/engine.py` - **EXISTS** - TournamentEngine with evaluate_all, promote, demote
  - `trading/tournament/store.py` - **EXISTS** - TournamentStore with stage management
  - `trading/learning.yaml:28-46` - Tournament stages (hourly cron at line 30)
  - `trading/agents/consensus.py:34` - WeightSource.ELO already defined
  - `trading/agents/consensus.py:39-62` - AgentWeightProfile.elo_rating to update

- [x] 2. **Backtest ranking engine** ✅ COMPLETE

  **What to do**:
  - Extend `trading/data/backtest.py` BacktestEngine to support multi-agent runs
  - Add ranking computation: Sharpe (primary), max_drawdown (secondary), win_rate (tertiary)
  - Store results in ArenaState

  **Acceptance Criteria**:
  - [ ] Run 3 agents in backtest, get ranked list
  - [ ] Ranking matches expected order by Sharpe

  **References**:
  - `trading/data/backtest.py:262-307` - BacktestEngine class
  - `trading/data/backtest.py:45-106` - BacktestResult with scoring

- [x] 3. **ELO rating integration** ✅ COMPLETE

  **What to do**:
  - Integrate ELO with `trading/agents/consensus.py` weight source
  - Update ELO after each tournament
  - K-factor: 32 (standard), decay per learning.yaml

  **Acceptance Criteria**:
  - [ ] ELO updates after tournament
  - [ ] Consensus router uses ELO weights

  **References**:
  - `trading/agents/consensus.py` - EnhancedConsensusRouter with weight sources

- [x] 4. **Stage promotion/demotion workflow** ✅ COMPLETE

  **What to do**:
  - Connect `trading/learning.yaml` tournament stages to Arena
  - Stage 1: Sharpe ≥1.5, min 50 trades, max 15% drawdown
  - Stage 2: Sharpe ≥1.8, min 100 trades, max 12% drawdown
  - Stage 3: Sharpe ≥2.0, min 200 trades, max 10% drawdown
  - Demotion if metrics drop below threshold for N consecutive days

  **Acceptance Criteria**:
  - [ ] Agent promoted when thresholds met
  - [ ] Agent demoted when below threshold

  **References**:
  - `trading/learning.yaml:28-46` - Tournament stage configuration

- [x] 5. **Arbitrage spread store with claim semantics** ✅ COMPLETE

  **What to do**:
  - Enhance `trading/storage/spreads.py` SpreadStore with atomic claim/release
  - Add TTL for claims (30 seconds)
  - Prevent double-execution

  **Acceptance Criteria**:
  - [ ] Claim succeeds once, fails on second attempt
  - [ ] Release clears claim

  **References**:
  - `trading/storage/spreads.py` - Existing SpreadStore implementation

- [x] 6. **Dual-leg execution engine** ✅ COMPLETE

  **What to do**:
  - Implement `execute_dual_leg(ArbTrade)` in `trading/execution/arbitrage.py`
  - Sequential execution with reconciliation
  - Track leg-level P&L

  **Acceptance Criteria**:
  - [ ] Both legs execute (or rollback on failure)
  - [ ] P&L calculated correctly

  **References**:
  - `trading/execution/arbitrage.py` - Existing arbitrage execution module
  - `trading/storage/arbitrage.py` - Arbitrage storage

- [x] 7. **Tournament scheduler integration** ✅ COMPLETE

  **What to do**:
  - Wire Arena.run_tournament() to existing `learning.yaml:30` hourly cron
  - Integrate with existing `trading/risk/governor.py` CapitalGovernor
  - Use APScheduler or existing cron infrastructure

  **Acceptance Criteria**:
  - [ ] Tournament runs automatically at scheduled time (hourly)
  - [ ] Results logged to structured log

  **References**:
  - `trading/learning.yaml:30` - Existing cron: `"0 * * * *"` (hourly)
  - `trading/risk/governor.py:1-30` - CapitalGovernor for capital allocation

---

### Wave 2 (Gym Core - Parameter Tuning)

- [x] 8. **Enhanced AdaptiveTuner with grid search** ✅ COMPLETE

  **What to do**:
  - Extend `trading/agents/tuning.py` AdaptiveTuner to support parameter ranges
  - Grid search over: RSI threshold (20-40), lookback_period (10-20), confidence_floor (0.4-0.8)
  - Return top N parameter sets
  - **KG Integration**: Log optimization runs to KG - track param_history per agent per regime

  **Acceptance Criteria**:
  - [ ] Grid search runs without errors
  - [ ] Returns best parameters by Sharpe
  - [ ] KG triples: agent-optimized_params, param-set_id, param-regime_context

  **References**:
  - `trading/agents/tuning.py:24-50` - Existing AdaptiveTuner class

- [x] 9. **Genetic algorithm parameter optimizer** ✅ COMPLETE

  **What to do**:
  - Create `trading/gym/optimizer.py` with GAOptimizer class (new top-level package)
  - Population: 20, Generations: 50, Mutation: 0.1, Crossover: 0.7
  - Fitness: Sharpe ratio on validation window
  - **KG Integration**: Store converged parameters with regime metadata for cross-regime pattern discovery

  **Acceptance Criteria**:
  - [ ] GA converges to better parameters
  - [ ] Parameters improve over initial

- [x] 10. **Parameter sweep API endpoint** ✅ COMPLETE

  **What to do**:
  - Add POST /gym/optimize endpoint
  - Accept: agent_name, param_ranges, method (grid/genetic)
  - Return: best_params, improvement_pct

  **Acceptance Criteria**:
  - [ ] Endpoint responds with optimization results
  - [ ] Best parameters returned

- [x] 11. **Walk-forward validation enhancement** ✅ COMPLETE

  **What to do**:
  - Enhance `trading/backtesting/walk_forward.py` with multiple train/test splits
  - Rolling window: 60 days train, 20 days test
  - Output: in-sample vs out-of-sample metrics

  **Acceptance Criteria**:
  - [ ] Walk-forward runs on agent
  - [ ] OOS metrics returned

  **References**:
  - `trading/backtesting/walk_forward.py:1-50` - Existing walk-forward implementation

- [x] 12. **Monte Carlo simulation** ✅ COMPLETE

  **What to do**:
  - Add MonteCarloSim class
  - Resample trade returns (bootstrap)
  - Return: 95% CI for Sharpe, max_drawdown

  **Acceptance Criteria**:
  - [ ] CI bounds computed
  - [ ] Results logged

---

### Wave 3 (Gym Advanced - Self-Reflection + Stress Tests)

- [x] 13. **LLM self-reflection pipeline** ✅ COMPLETE

  **What to do**:
  - Create `trading/gym/reflection.py` with SelfReflectionAgent
  - Query trade history via TradeReflector
  - Send to LLM with prompt: "Analyze these trades, identify patterns, suggest improvements"
  - Store insights with tags
  - **KG Integration**: Persist insights to TradingKnowledgeGraph with regime context for historical pattern matching

  **Acceptance Criteria**:
  - [ ] LLM returns actionable insights
  - [ ] Insights stored in memory
  - [ ] KG triples: agent-learned_insight, insight-tagged_regime, insight-linked_trades

- [x] 14. **Trade outcome analysis agent** ✅ COMPLETE

  **What to do**:
  - Analyze: entry timing, exit timing, position sizing, regime fit
  - Categorize: good_entry, bad_entry, good_exit, bad_exit, size_issue, regime_mismatch
  - Aggregate stats per agent

  **Acceptance Criteria**:
  - [ ] Trades categorized correctly
  - [ ] Stats aggregate per agent

- [x] 15. **Stress test scenario injector** ✅ COMPLETE

  **What to do**:
  - Create `trading/gym/stress.py` with StressTestEnvironment
  - Inject scenarios into historical data
  - Run agents through scenarios
  - **KG Integration**: Log stress test outcomes to KG - correlate which strategies worked in which regimes historically

  **Acceptance Criteria**:
  - [ ] Scenario injection works
  - [ ] Agent performance under stress measured
  - [ ] KG stores: scenario-ran_stress-test, regime-tested_regime, agent-outcome_metrics

- [x] 16. **Flash crash scenario** ✅ COMPLETE

  **What to do**:
  - Inject 10% drop over 5 minutes
  - Test stop-loss, exit rules
  - Measure: time to exit, slippage realized

  **Acceptance Criteria**:
  - [ ] Agents handle flash crash
  - [ ] Exit rules trigger correctly

- [x] 17. **Volatility spike scenario** ✅ COMPLETE

  **What to do**:
  - Inject 3x normal volatility
  - Test position sizing adjustments
  - Measure: size reduction effectiveness

  **Acceptance Criteria**:
  - [ ] Volatility spike detected
  - [ ] Sizing adjusts appropriately

- [x] 18. **Gap open scenario** ✅ COMPLETE

  **What to do**:
  - Inject 5% overnight gap
  - Test gap fill strategies
  - Measure: fill quality, slippage

  **Acceptance Criteria**:
  - [ ] Gap scenario runs
  - [ ] Agent response measured

---

### Wave 4 (Integration - Multi-Agent + Full Wiring)

- [x] 19. **Multi-agent backtest capability** ✅ COMPLETE

  **What to do**:
  - Enhance BacktestEngine to run multiple agents
  - Aggregate opportunities across agents
  - Track per-agent metrics

  **Acceptance Criteria**:
  - [ ] 5+ agents run in backtest
  - [ ] Per-agent metrics computed

- [x] 20. **Consensus voting backtest simulation** ✅ COMPLETE

  **What to do**:
  - Use `trading/backtesting/consensus_sim.py` 
  - Run consensus in backtest mode
  - Measure: consensus frequency, quality

  **Acceptance Criteria**:
  - [ ] Consensus simulated in backtest
  - [ ] Vote quality measured

  **References**:
  - `trading/backtesting/consensus_sim.py` - Existing consensus simulation

- [x] 21. **Arena-Gym integration** ✅ COMPLETE

  **What to do**:
  - Connect Arena → Gym: after tournament, identify underperformers
  - Connect Gym → Arena: optimized params fed back to tournament
  - Full loop: optimize → compete → analyze → re-optimize

  **Acceptance Criteria**:
  - [ ] Optimization runs for underperformers
  - [ ] New params used in next tournament

- [x] 22. **Real-time spread monitoring** ✅ COMPLETE

  **What to do**:
  - Add WebSocket endpoint for spread updates
  - Push new spreads to connected clients
  - Dashboard-friendly format

  **Acceptance Criteria**:
  - [ ] Spreads pushed in real-time
  - [ ] Client receives updates

- [x] 23. **Unified arbitrage DSL** ✅ COMPLETE

  **What to do**:
  - Extend `trading/strategies/dsl.py` for arbitrage patterns
  - Pattern: WHEN condition THEN action
  - Compile to execution plan

  **Acceptance Criteria**:
  - [ ] DSL parses arb patterns
  - [ ] Compiles to executable plan

  **References**:
  - `trading/strategies/dsl.py` - Existing DSL agent implementation

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE.

- [ ] F1. **Plan Compliance Audit** — Verify all deliverables match plan
- [ ] F2. **Code Quality Review** — TypeScript/Python linting, no regressions
- [ ] F3. **Integration Testing** — Arena → Gym → Arbitrage flow works
- [ ] F4. **Scope Fidelity Check** — No creep beyond defined scope

---

## Commit Strategy

- Wave 1: `feat(arena): add tournament core + arbitrage execution`
- Wave 2: `feat(gym): add parameter optimization + walk-forward`
- Wave 3: `feat(gym): add self-reflection + stress tests`
- Wave 4: `feat(integration): multi-agent backtest + full wiring`

---

## Success Criteria

```bash
# Arena tournament runs
python -c "from arena.tournament import Tournament; t = Tournament(); t.run_daily()"

# Gym optimization runs
python -c "from gym.optimizer import ParameterOptimizer; opt = ParameterOptimizer(); opt.optimize('rsi_scanner')"

# Arbitrage executes
curl -X POST http://localhost:8080/api/arb/execute -d '{"observation_id": 1, "agent_name": "cross_platform_arb"}'
```
