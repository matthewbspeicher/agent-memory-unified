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

## Pointers

- Audit (full): `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- Audit dimension scoreboard: §1 of the audit
- Audit recommended sequence: §5 of the audit
- This track's spec: `conductor/tracks/intelligence_memory/spec.md`
- This track's plan: `conductor/tracks/intelligence_memory/plan.md`
- Memory entries: `reference_agent_readiness_audit.md`, `project_design_md_workflow.md`, `reference_moltbook.md`, `feedback_parallel_opencode_stream.md`
