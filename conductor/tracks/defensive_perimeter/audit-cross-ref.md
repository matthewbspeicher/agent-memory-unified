# Cross-reference: Agent-Readiness Audit ↔ Defensive Perimeter (Phase A)

**Created:** 2026-04-10
**By:** Claude Code
**Purpose:** Quick cross-reference for coordinating the `defensive_perimeter` track with the agent-readiness audit's recommendations. Same pattern as `conductor/tracks/intelligence_memory/audit-cross-ref.md`.

## The two documents

| Document | Path | Type | Status |
|---|---|---|---|
| Defensive Perimeter v2 spec | `conductor/tracks/defensive_perimeter/spec.md` | Implementation spec | v2 — addresses all 8 concerns from Claude Code brainstorm review |
| Defensive Perimeter plan | `conductor/tracks/defensive_perimeter/plan.md` | Task plan | 3 tasks (rate limiting, audit logging, kill-switch) |
| Agent-readiness audit | `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md` | Read-only audit | Committed `df4bb44` |

This track **directly implements** the audit's Phase A recommendations. It is the first track to exist specifically to close audit findings, rather than a parallel work stream (like `intelligence_memory`) that happens to overlap with audit territory.

## Audit findings this track targets

| Audit dimension | Risk | Phase A coverage |
|---|---|---|
| 🔴 #2 Rate limiting | Critical | **Closes** — tiered `slowapi` middleware with anon/verified/master tiers |
| 🔴 #5 Write surface protection | Critical | **Partial close** — two-step confirmation on `/risk/kill-switch` + global Redis kill-switch flag that blocks all POST/PUT/DELETE; audit logging on the first 5 highest-risk routes (kill-switch, orders, trades, agents/scan, competition/settle). Remaining ~35 write routes are a follow-up. |
| 🟠 #6 Audit logs on writes | High | **Closes for instrumented routes** — `@audit_event` decorator with dual sink (structured `log_event()` + `audit_logs` Postgres table). Remaining ~35 routes are a mechanical backfill follow-up. |
| 🔴 #8 Per-agent resource limits — *cross-cutting LLM cost ceiling* | Critical | **Not addressed** — the per-scan `max_calls_per_scan` enforcement from the intelligence_memory track addresses the per-scan level, but global monthly token quotas and per-agent cost ceilings remain open. Not in Phase A scope. |
| 🟠 #1 Identity & auth | High | **Consumes the attribution-only `verify_agent_token` foundation** from intelligence_memory Phase 4. Per-agent rate limiting is best-effort until Phase B lands real token verification — documented explicitly in the spec per the Phase A review feedback. |

## Audit findings this track does NOT address

| Audit dimension | Risk | Why out of scope |
|---|---|---|
| 🟡 #3 Agent-readable docs | Medium | Separate track (`public_surface`) owns `FOR_AGENTS.md` and `/.well-known/agents.json` |
| 🟢 #4 Content to consume | Low | Already adequate; `project-feed/` work stream handles publication surface |
| 🟡 #7 Concurrency model | Medium | Not a defensive-perimeter concern; current asyncio + Semaphore(5) is adequate |
| 🟡 #9 Observability | Medium | Separate track (`abuse_response`) owns per-agent Grafana dashboards |
| 🟡 #10 Inter-agent coordination | Medium | Separate concern; `consensus_threshold` review belongs elsewhere |

## Coordination with other tracks

### Depends on
- **Nothing blocking.** Intelligence_memory Phase 1-4 is committed at `f9b5386`. This track can begin Task 1 once the spec nits in the Phase A review are addressed.

### Unblocks
- **`agent_identity` track (audit Phase B)** — Phase A's `verify_agent_token` usage for bucket keys creates the incentive to upgrade it to real verification. Phase B's work is "take the attribution-only foundation and make it authoritative."
- **`public_surface` track (audit Phase D prep)** — Phase A's rate limiting middleware with the anonymous tier (10 req/min, read-only allowlist) is a prerequisite for exposing any curated public endpoints. The allowlist pattern defined in Phase A carries forward.
- **`moltbook_publisher` track (work stream ε)** — The audit-log decorator from Phase A can be reused to instrument the publisher script itself, so every Moltbook POST attempt is traceable.
- **Inviting any external agent traffic via Moltbook** — the **hard gate** in the audit's recommended sequence is "no external agents until rate limiting, per-agent identity, and the defensive_perimeter work land." This track is that landing.

### Shares primitives with
- **`intelligence_memory` track** — Uses the same `log_event()` helper from `trading/utils/logging.py`. The `audit_logs` Postgres table should share the same migration mechanism as the `kg` schema from intelligence_memory (likely inline `CREATE TABLE IF NOT EXISTS` in storage layer, or `scripts/init-trading-tables.sql` — the cross-ref notes this is TBD). Consistency matters for Railway deployment.

### Explicitly does NOT own
- **Real per-agent authentication.** Phase A ships attribution-only per-agent rate limiting with a spec note that the bucket is bypassable. Audit Phase B (separate `agent_identity` track, not yet specced) owns real token verification.
- **The existing ~35 write routes without audit instrumentation.** Phase A instruments the 5 highest-risk routes; the rest are a follow-up.
- **Abuse response playbooks.** The abuse contact, incident runbook, and Sentry alerting rules belong to the `abuse_response` track (work stream ζ).
- **External-facing documentation.** `FOR_AGENTS.md` and `/.well-known/agents.json` belong to `public_surface`.

## Hard gate restated

Per the audit's recommended sequence: **do not invite external agent traffic** (no Moltbook posts announcing the project, no `FOR_AGENTS.md` landing page made discoverable, no arena participation endpoints opened) **until this track (defensive_perimeter / Phase A), the agent_identity track (Phase B), and the public_surface track (Phase D prep) have all landed.** The `project-feed/` directory can be seeded with draft posts before then — publication is what the gate blocks.

## Pointers

- Audit (full): `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- Audit dimension scoreboard: §1 of the audit
- Audit recommended sequence: §5 of the audit
- This track's spec: `conductor/tracks/defensive_perimeter/spec.md`
- This track's plan: `conductor/tracks/defensive_perimeter/plan.md`
- Sibling track cross-ref: `conductor/tracks/intelligence_memory/audit-cross-ref.md`
- Memory entries: `reference_agent_readiness_audit.md`, `reference_moltbook.md`, `feedback_parallel_opencode_stream.md`
