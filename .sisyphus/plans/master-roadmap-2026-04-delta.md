# Master Roadmap — Delta (2026-04-14)

**Supersedes**: `master-roadmap-2026-04.md` (still archived; this file is the source of truth going forward).

**Verification basis**: Direct grep/test against `main` at commit `0c4a385` on 2026-04-14. All "DONE" items below were confirmed with filepath+line references.

**Realistic remaining effort**: ~55–65h (original roadmap claimed 107h; ~45h is already shipped).

---

## §A — Verify & close (0h, just check off)

Confirm via the cited path, then mark done in the prior roadmap / any tracking doc.

| Item | Evidence |
|---|---|
| **0.1** Fix `test_orders_delete_correct_scope_allowed` | Test doesn't exist — pytest collection returns "no match". Either renamed or removed; suite is at 2318 passing. |
| **1.1** Shadow-mode agent promotion | `trading/agents/runner.py:164::update_agent_shadow_mode` with test `test_runner.py:87`. Route `shadow.py:148` calls it. |
| **2.1a** Portfolio-level kill switch | `trading/storage/portfolio_state.py::PortfolioStateStore` + `risk/rules.py::PortfolioDrawdownKillSwitch`; full test file `test_portfolio_drawdown.py`. |
| **2.1c** Correlation enforcement gate | `trading/risk/correlation_gate.py::CorrelationGate`, registered in `risk/config.py:36`. |
| **2.2** Wire Signal Pipeline (MinerConsensusAggregator) | `trading/integrations/bittensor/consensus_aggregator.py`, wired in `app.py:529-555`; unit + E2E tests exist. |

---

## §B — Branch hygiene (~30min)

| Item | Action |
|---|---|
| **0.2a** `feature/critical-fixes` | 1 commit (`3afe079`). Fast-forward merge to main, run suite, done. |
| **0.2b** `feature/mission-control-backend` | **Do not merge.** Content is already on main (MC dashboard via `3a163d1`+`e5b8b9c`; aggregator via `68c4fb6`). Instead: `git diff main..feature/mission-control-backend --stat`, cherry-pick only genuinely novel commits, then delete the branch. |

---

## §C — Small & open (~5h total)

| Item | Effort | Notes |
|---|---|---|
| **0.3** Memory preflight — `LocalMemoryStore._preflight_check()` + `/memory/health` | 1h | Accurate as-written. pgvector extension + HNSW index + `STA_MEMORY_TABLE` checks. |
| **1.3** Consolidator LLM wiring | 1–2h | `consolidator.py:57-59` still uses `hasattr(self.llm, "agenerate_text")` ducktyping. Swap in `LLMClient` type hint and `agenerate()` call; drop fallback branch. |
| **3.3** Learning FIXMEs | 2h | **Three** FIXMEs, not two — the roadmap missed `memory_client.py:95`. Also `strategy_index.py:18` and `memory_linter.py:19`. Implement tag-based SDK query methods then replace. |

---

## §D — Material & open (~10–13h)

| Item | Effort | Notes |
|---|---|---|
| **1.2** Achievements per-agent scoping | 2–3h | Partial: `create_tracker(user_id="default")` already takes `user_id`. Real gap is per-*agent* scoping (separate dimension from user) + DB persistence. |
| **1.5** Arbitrage dual-leg execution | 4–5h | `arbitrage.py:47-57` literally logs "dual-leg execution not wired — returning claim-only." `ArbExecutor` class + state tracking + partial-fill/leg2-failure handling. **Real-money blast radius — test thoroughly.** |
| **2.1b** Consecutive-loss streak DB persistence | 1–2h (not 3h) | Core throttling already in `learning/strategy_health.py:60-73` (`max_consecutive_losses=5`, 48h cooldown). Remaining: the DB-persisted streak fields per the go-trader plan §2 spec. |
| **1.4** Lab-page tabs (Backtest / Validation / Logs) | 2–3h | UI work — **opencode parallel-work conflict risk** per `feedback_parallel_opencode_stream`. Coordinate before starting. |

---

## §E — Quality sweep (~12h)

| Item | Effort | Notes |
|---|---|---|
| **3.1** Frontend Vitest setup + 20+ unit tests | 6–8h | Zero React unit tests today. Priority: `useMissionControl.ts`, `missionControl.ts`, `Lab.tsx`, `Forge.tsx`. |
| **3.2** API route test coverage | 4–5h | Several listed routes still thin (`arbitrage`, `achievements`). Follow existing `httpx.AsyncClient` + `ASGITransport` pattern. |

---

## §F — Backlog (by business value)

Ordered for prioritization, not sequencing.

| Rank | Item | Effort | Rationale |
|---|---|---|---|
| 1 | **4.1** BitGet broker adapter | 16h | High crypto value; closes a broker gap |
| 2 | **4.6** Declarative rules engine | 8–10h | Defensive — pre-trade validation safety net |
| 3 | **2.3** MemClaw memory architecture | 6–8h | **On hold** per `project_moltbook_on_hold` memory — confirm with user before starting |
| 4 | **4.3** WebSocket spreads streaming | 3–4h | Mission Control live-updates |
| 5 | **4.4** Knowledge graph real data | 3–4h | Removes a mock fallback |
| 6 | **4.2** Tax CSV logging | 8h | Compliance — only urgent near year-end |
| 7 | **4.5** AI automation / gamification bundle | ~20h | De-dupe with §D #1 (achievements); split further before picking up |

---

## Updated dependency graph

```
§A (verify/close)          →  no work, just close tickets
§B (branch hygiene)        →  independent; ~30min
§C (0.3, 1.3, 3.3)         →  fully parallel
§D (1.2, 1.5, 2.1b, 1.4)   →  parallel; 1.5 warrants careful review
§E (3.1, 3.2)              →  parallel with each other and with §D
§F (backlog)               →  prioritize by rank, not dependency
```

## Updated time estimates

| Phase | Effort | Cumulative |
|---|---|---|
| §A verify/close | 0h | 0h |
| §B branch hygiene | 0.5h | 0.5h |
| §C small/open | 5h | 5.5h |
| §D material/open | 10–13h | 15–18h |
| §E quality sweep | 10–13h | 25–31h |
| §F backlog (if all done) | 45–55h | 70–86h |

**Foreground work (§A–§E)**: ~25–31h. **With backlog**: ~70–86h.

## Source-of-truth baseline (2026-04-14)

Facts confirmed at review time — update when these change:

- Unit tests: **2318 passing** (not 2303 as the prior roadmap stated)
- Most recent main commit: `0c4a385 feat(mcp): add alpha vantage mcp server`
- Schema parity guarded by `trading/tests/unit/test_storage/test_schema_parity.py`
- Alpha Vantage parity plan: **fully closed** (Tasks 1+2 previously, Task 3 today)
