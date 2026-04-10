# Feature Implementation Plan: AI Automation + Gamification

## 🎯 Overview
Implement 6 features across 2 phases. Phase 1 ships fastest value, Phase 2 adds depth.

---

## Phase 1: Quick Wins (1-2 sprints)

### Feature 7: Natural Language Trade Commands
**Priority**: HIGH | **Effort**: Medium

Parse natural language into executable trades.

```
User: "buy Bitcoin if sentiment > 0.7"
System: → { action: "BUY", symbol: "BTCUSD", condition: { field: "sentiment", op: ">", value: 0.7 } }
```

**Components:**
- `trading/engine/nl_parser.py` — NLI parser with regex + keyword matching
- `trading/engine/condition_evaluator.py` — Evaluate conditions against market data
- `POST /engine/v1/orders/nl` endpoint

**Ship: Day 2**

---

### Feature 10: Achievement System
**Priority**: HIGH | **Effort**: Low

Badge tracking and reward system.

**Achievements:**
| ID | Name | Criteria |
|----|------|----------|
| `first_trade` | First Blood | Complete first trade |
| `ten_bagger` | Ten Trades | Execute 10 trades |
| `streak_5` | On Fire | Profitable 5 days consecutively |
| `sharpe_king` | Sharpe Master | Best Sharpe ratio in month |
| `comeback_kid` | Comeback | Recover from 10%+ drawdown |
| `diamond_hands` | Diamond Hands | Hold position 24h+ with 5%+ profit |

**Components:**
- `trading/achievements/registry.py` — Achievement definitions
- `trading/achievements/tracker.py` — Track and unlock badges
- `GET /api/v1/achievements` endpoint
- `GET /api/v1/achievements/{user}/badges`

**Ship: Day 1**

---

## Phase 2: Deeper Features (2-3 sprints)

### Feature 11: Trading Journal AI
**Priority**: MEDIUM | **Effort**: Medium

Auto-tag trades, generate weekly summaries.

**Components:**
- `trading/journal/tagger.py` — ML-based trade categorization (winner/loser/scalp/swing)
- `trading/journal/summarizer.py` — Weekly insight generation
- `POST /api/v1/journal/analyze` — Analyze single trade
- `GET /api/v1/journal/weekly` — Get weekly summary

**Ship: Day 5**

---

### Feature 8: Memory-Triggered Strategies
**Priority**: MEDIUM | **Effort**: High

Execute trades when memory patterns emerge.

```
Trigger: "similar setup 3x = bullish"
Query memories for: { type: "decision", outcome: "bullish", similarity: 0.8 }
```

**Components:**
- `trading/strategies/memory_trigger.py` — Trigger engine
- `trading/strategies/pattern_matcher.py` — Find similar memories
- Configuration in `strategies.yaml`

**Ship: Day 7**

---

### Feature 9: Self-Critic Agent
**Priority**: MEDIUM | **Effort**: High

Second AI reviews every trade, logs counterarguments.

**Flow:**
1. Primary agent submits trade
2. Critic agent evaluates: "Should this trade be allowed?"
3. Logs: { trade_id, verdict: APPROVE/REJECT, reasoning, counterarguments }
4. If REJECT → prompt user confirmation

**Components:**
- `trading/agents/critic.py` — LLM-based critic (configurable model)
- `trading/agents/critic_store.py` — Persist critiques
- `GET /api/v1/trades/{id}/critique`

**Ship: Day 8**

---

### Feature 12: Mini Arcade
**Priority**: LOW | **Effort**: Medium

Agents compete in simple games.

**Games:**
- **RPS Tournament** — Rock-Paper-Scissors bracket, winner takes pot
- **Prediction Market** — Bet on agent predictions, pool of fake $

**Components:**
- `trading/arcade/games.py` — Game logic
- `trading/arcade/leaderboard.py` — Arcade rankings
- `GET /api/v1/arcade/games`
- `POST /api/v1/arcade/rps` — Play RPS

**Ship: Day 6**

---

## 📦 Dependencies

| Feature | Depends On |
|---------|------------|
| Memory-Triggered | MemClaw (done ✅) |
| Trading Journal | None |
| Self-Critic | LLM config (env var) |
| Mini Arcade | None |

---

## 🗓️ Timeline

| Day | Feature |
|-----|---------|
| 1 | Achievement System |
| 2 | NL Trade Commands |
| 3-4 | Rest + Polish |
| 5 | Trading Journal AI |
| 6 | Mini Arcade |
| 7 | Memory-Triggered |
| 8 | Self-Critic |
| 9 | Integration Testing |

---

## 🚀 Next Steps

1. **Approve plan** → Start Day 1: Achievement System
2. **Pick 1 feature** → I'll prioritize just that one first
3. **Adjust scope** → Remove any features you don't want