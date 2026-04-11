# Cross-reference: Agent-Readiness Audit ↔ Intelligence/Memory v2

**Created:** 2026-04-10
**By:** Claude Code (synthesis), running in parallel with Gemini's intelligence_memory track
**Purpose:** Quick cross-reference so this track's work can be coordinated with the agent-readiness audit's findings without duplicating either document.

## The two documents

| Document | Path | Type | Status |
|---|---|---|---|
| Intelligence/Memory v2 spec | `conductor/tracks/intelligence_memory/spec.md` | Implementation spec | v2 — incorporates 5 critical fixes from Claude Code review |
| Intelligence/Memory v2 plan | `conductor/tracks/intelligence_memory/plan.md` | Phased task plan | Phase 1 Task 1 in flight at writing time |
| Agent-readiness audit | `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md` | Read-only audit | Committed `df4bb44` |

Both documents are intended to be read by future sessions touching this surface. They are **complementary, not duplicative**:

- The **spec/plan** describes new code being added (KG, L0/L1 context, ReACT agent, dedup, WAL).
- The **audit** describes the *existing* surface (~40 write endpoints, current auth model, rate limiting absence, observability sparsity) and the gaps that exist regardless of whether the intelligence/memory work lands.

## Where the two streams overlap

Mapping audit findings → Gemini v2 coverage:

| Audit dimension | Risk | Gemini v2 coverage | Remaining gap |
|---|---|---|---|
| #1 Identity & auth | 🟠 High | ✅ "Agent Identity" guardrail in spec §D — scoped to KG ops | Extend per-agent identity beyond KG to *all* routes (Phase B in audit's sequence) |
| #2 Rate limiting | 🔴 **Critical** | ❌ Not addressed | Phase A in audit's sequence — entirely separate work stream |
| #3 Agent-readable docs | 🟡 Medium | ❌ Not addressed | `FOR_AGENTS.md` task — independent of this track |
| #5 Write surface / kill-switch | 🔴 **Critical** | ❌ Not addressed | Phase A — separate work stream |
| #6 Audit logs on writes | 🟠 High | ✅ "Structured Logging" guardrail in spec §D — for new write paths | Retroactive instrumentation pass on existing ~40 routes (Phase A's `@audit_event` decorator) |
| #8 Per-agent resource limits | 🔴 **Critical** | ✅ "LLM Budgeting" guardrail in spec §D — `max_calls_per_scan`, `monthly_token_quota` in `agents.yaml` | Enforcement point needs to be wired into `trading/llm/client.py` or `trading/agents/base.py`; partial coverage only |
| #10 Inter-agent coordination | 🟡 Medium | ❌ Not addressed | `consensus_threshold` review — independent of this track |

**Reading:** Gemini's v2 covers the right architectural layer for findings #1, #6, and #8 — but only for the *new* code in this track. The *existing* surface remains uncovered. The audit's Phases A and B exist specifically to fix that gap and are gating prerequisites for opening the trading API to external agents.

## Coordination notes for this track

### What this track SHOULD do (already in v2 spec)

- ✅ Use `JournalIndexer` as the canonical vector wrapper (per `reference_vector_index_canonical.md`).
- ✅ Put the KG in Postgres `kg` schema, not SQLite.
- ✅ Pin to Python 3.13 and Claude 4.6 models.
- ✅ Emit `log_event()` structured events on every memory write, KG update, and context generation.
- ✅ Wire LLM budgets into `agents.yaml` and enforce them at the LLM call site.
- ✅ Gate KG ingestion behind `STA_KNOWLEDGE_GRAPH_ENABLED` (default false).
- ✅ Add a `sweep_expired()` background task for KG sprawl mitigation.

### What this track should NOT take ownership of

These are explicitly the audit's separate work streams (Phases A, B, D). Do not bundle them into the intelligence_memory track:

- **Rate limiting middleware** — needs `slowapi` or equivalent on the FastAPI app, not on `trading/agents/`.
- **Kill-switch confirmation flow** — refactor of `trading/api/routes/risk.py:28`.
- **The `@audit_event` decorator for retroactive instrumentation** of existing write routes — separate, broad-touching change.
- **`FOR_AGENTS.md`** at the repo root and `/.well-known/agents.json` static file.
- **Moltbook publisher script** — separate work stream described in `reference_moltbook.md`.

### Coordination opportunities to flag

- **Structured logging primitives.** If this track adds helper functions for emitting `kg.triple_added`, `memory.deduplicated`, `context.generated` events, those helpers can be lifted into a shared `trading/utils/audit.py` (or similar) so the audit's Phase A `@audit_event` decorator reuses them. Worth keeping the event-emission code free of intelligence-specific imports.
- **Per-agent identity foundation.** If this track adds any per-agent identity wrapper to gate KG read/write ops, design it so the same primitive can extend to other routes in audit Phase B. The dormant JWT path at `trading/api/dependencies.py:87-114` is the natural foundation; consider resurrecting it as part of this track's identity work, even if only the KG endpoints initially consume it.
- **LLM budget enforcement point.** If `max_calls_per_scan` is enforced inside the LLM client (`trading/llm/client.py`) rather than at the agent level, all callers benefit automatically — including any external-agent traffic that triggers `/agents/{name}/scan`. Recommend the client-level enforcement point.

## Hard gate

Per the audit's recommended sequence: **do not invite external agent traffic** (no Moltbook posts, no FOR_AGENTS.md announcement, no public arena participation endpoints) **until rate limiting (Phase A), per-agent identity (Phase B), and this track's intelligence/memory Phase 2-3 (Phase C in the audit's sequence) have all landed.** That's the gate.

## Verification status (2026-04-10 evening)

After Gemini reported Phases 1-3 complete, Claude Code did a verification spot-check across the v2 spec's claims. **The work is real and substantial.** Status per claim:

| Claim | Verified | Evidence |
|---|---|---|
| WAL mode + busy_timeout on SQLite | ✅ | Committed `1d70444`, `aa49b11`; verify script asserts `PRAGMA journal_mode == "wal"` |
| Content-hash dedup with `access_count` increment | ✅ | `trading/storage/memory.py:208-242`; verify script asserts second store returns same id + `deduplicated=True` |
| Structured logging events `memory.write` / `memory.deduplicated` / `kg.triple_added` | ✅ | `memory.py:226`, `memory.py:294`, `knowledge_graph.py:223` — all use `log_event()` |
| Temporal Knowledge Graph (entities + triples + sweep) | ✅ | Committed `ef52c19`; verify script tests sweep with `valid_to` in past, asserts return value |
| KG ingestion writers wired into TaoshiBridge / MinerEvaluator / RegimeMemoryManager | ✅ | Committed `89834c8`, `ef04e58`, `2309532`, `f30482e`; runtime guards at `taoshi_bridge.py:163,199`, `evaluator.py:183`, `market_regime.py:169` |
| `STA_KNOWLEDGE_GRAPH_ENABLED` feature flag (default false) | ✅ | `config.py:213` `knowledge_graph_enabled: bool = False`; threaded as `kg_enabled` constructor param to all writers (note: env var → snake_case → constructor rename, see `reference_sta_env_var_convention.md`) |
| L0/L1 generation in `SqlPromptStore` using `JournalIndexer` | ✅ | `prompt_store.py:155-185` `generate_agent_context()`; verify script asserts generated context contains "## Identity" + agent name + "## Recent Performance" |
| L0/L1 wired into `LLMAgent.system_prompt` + agent startup priming | ✅ | Committed `6f852c4`, `47d65fc` |
| `JournalIndexer` as canonical vector wrapper | ✅ | Used in `prompt_store.py` constructor; matches `reference_vector_index_canonical.md` rule, no parallel wrappers introduced |
| LLM budget enforcement (`max_calls_per_scan`) | ✅ | `agents/base.py:63-69` raises `RuntimeError` on overflow; `agents/config.py:40` `Field(default=5, ge=1, le=50)`; threaded through `models.py:80`, `config.py:245` |
| Verify script with real assertions | ✅ | `trading/tests/verify_intelligence_loop.py` (~145 lines, 4 test functions covering WAL / dedup / KG sweep / L0+L1) |
| Postgres dual-backend refactor for `TradingKnowledgeGraph` | ⚠️ Partial | The committed `ef52c19` is SQLite-only. The dual-backend refactor exists in the working tree (`git status` shows `M trading/storage/knowledge_graph.py`) but is uncommitted at verification time. Code-shape not fully read by Claude Code |
| ReACT analyst upgrade to `claude-opus-4-6` + `query_knowledge_graph` tool | ⚠️ Not personally verified | Claimed in user-relayed Gemini summary; Claude Code did not read `trading/strategies/react_analyst.py` during the verification pass |

**Verify script coverage gaps (worth knowing for regression tracking):** the script does NOT exercise the `STA_KNOWLEDGE_GRAPH_ENABLED` runtime gating, the LLM budget enforcement path, the KG ingestion writers in their actual integration sites, the structured event emission output (it doesn't capture log lines), the Postgres backend (uses SQLite), or the ReACT agent. All of these are *implemented* but *not asserted* by the test suite.

**Audit findings closed by this verification:**
- 🟠 #6 Audit logs on writes — closed for the new memory/KG write paths added by Gemini's track. **Not closed** for the existing ~40 write routes — that remains audit Phase A territory.
- 🔴 #8 Per-agent resource limits — closed at the per-agent-config level (`max_calls_per_scan` enforced in `base.py`). **Not closed** at the cross-cutting level (no monthly token quota enforcement, no global LLM cost ceiling).

**Audit findings still open after this verification:**
- 🔴 #2 Rate limiting (none added — separate work stream, audit Phase A)
- 🔴 #5 Write surface protection / kill-switch confirmation (separate work stream, audit Phase A)
- 🟠 #1 Identity & auth — partial coverage planned for Phase 4 (agent-level identity migration); broader API-wide identity remains audit Phase B

## Pointers

- Audit (full): `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- Audit dimension scoreboard: §1 of the audit
- Audit recommended sequence: §5 of the audit
- This track's spec: `conductor/tracks/intelligence_memory/spec.md`
- This track's plan: `conductor/tracks/intelligence_memory/plan.md`
- Memory entries: `reference_agent_readiness_audit.md`, `project_design_md_workflow.md`, `reference_moltbook.md`, `feedback_parallel_opencode_stream.md`
