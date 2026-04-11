# Cross-reference: Agent-Readiness Audit ↔ Agent Identity (Phase B)

**Created:** 2026-04-10
**By:** Claude Code
**Purpose:** Map this track's scope to the agent-readiness audit. Same pattern as the other cross-ref docs under `conductor/tracks/*/audit-cross-ref.md`.

## Track identity

This is **audit Phase B** — the track that closes finding #1 (Identity & auth) by replacing the attribution-only foundation with real per-agent authentication + scope-gated authorization. Named `agent_identity` per the user's confirmed naming on 2026-04-10.

## Audit findings this track targets

| Audit dimension | Risk | Coverage |
|---|---|---|
| 🟠 #1 Identity & auth | High | **Closes** — pre-shared token storage in Postgres `identity.agents`, hash-based verification via `resolve_identity`, scope-tagged authorization via `require_scope(...)`, registration/revocation/rotation endpoints, back-compat with the master `STA_API_KEY`. After this track lands, the attribution-only `verify_agent_token` from intelligence_memory Phase 4 is no longer the only identity mechanism — it stays for the 3 KG read endpoints that use it but is no longer load-bearing. |
| 🔴 #5 Write surface protection | Critical | **Meaningful partial close** — 11 highest-risk write endpoints migrate from `verify_api_key` to `require_scope(...)`, adding per-scope authorization on top of authentication. The mechanical backfill of the remaining ~30 write routes remains a follow-up. Combined with `defensive_perimeter`'s audit decorator + rate limiting + kill-switch protection, this brings the critical write surface from "one shared key gates everything" to "scope-gated per agent." |
| 🔴 #2 Rate limiting (per-agent) | Critical | **Closes the bypassability gap** from defensive_perimeter — Phase A's per-agent rate limiting used `X-Agent-Token` as the bucket key, which was bypassable because any string was accepted as an agent identity. After Phase B, the bucket key uses the **verified** agent name from `resolve_identity`, so unknown tokens fall back to IP-based anonymous buckets. A malicious caller rotating token values no longer resets their bucket. |
| 🟠 #6 Audit logs on writes | High | **Enhances existing coverage** — defensive_perimeter's `@audit_event` decorator currently logs with attribution-only identity. Task 8 of this track updates the decorator to pull the verified `agent_id` from `resolve_identity`, so audit events meaningfully attribute actions. The audit trail goes from "who had the master API key" to "which specific registered agent took this action." |

## Audit findings this track does NOT address

| Audit dimension | Risk | Why out of scope |
|---|---|---|
| 🔴 #5 — the remaining ~30 write routes | Critical | Mechanical backfill; follow-up after Phase B lands. Not in the spec to avoid scope creep. |
| 🔴 #8 Per-agent resource limits (cross-cutting) | Critical | Per-scan LLM budgets are in `intelligence_memory`. Global cost ceilings and monthly quotas are a separate concern. |
| 🟡 #3 Agent-readable docs | Medium | `public_surface` track owns `FOR_AGENTS.md`. |
| 🟢 #4 Content to consume | Low | Adequate. |
| 🟡 #7 Concurrency model | Medium | Adequate for current scale. |
| 🟡 #9 Observability | Medium | `abuse_response` track will own per-agent Grafana dashboards. |
| 🟡 #10 Inter-agent coordination | Medium | Internal concern. |

## Dependencies

### Hard dependencies (must land before this track merges)

- **`defensive_perimeter` Phase A** — needs rate limiter to exist so this track can update its bucket key function. Phase A landed at `02541e2` (pending verification). **If verification reveals divergence** from the Phase A v2 spec, this track's Task 7 needs to adapt to the actual shape of the middleware.
- **Postgres connection pool** — same `STA_DATABASE_URL` as the trading engine. The `identity` schema migration lands in `scripts/migrations/add-agent-identity.sql`.

### Soft dependencies

- **`intelligence_memory` Phase 4** — the attribution-only `verify_agent_token` function at `trading/api/auth.py:37-53` stays in place (back-compat for the 3 KG read endpoints). This track adds `resolve_identity` alongside rather than replacing.
- **`public_surface` track** — will benefit from identity-awareness as a follow-up. Public endpoints ship with anonymous-only auth at first; a later iteration upgrades them to optionally accept verified agents for higher rate limit tiers.

## Unblocks

- **Moltbook publication gate** — this is **the single largest outstanding gate** for inviting external agent traffic. After this track lands, the remaining gates are: `public_surface` implementation (specced), `moltbook_publisher` implementation (specced), 2-3 polished posts (one draft exists), and the human Moltbook registration step. None of those are the same order of complexity as this track.
- **Retroactive write-route instrumentation** — once `require_scope(...)` is in the codebase, backfilling the remaining ~30 write routes becomes mechanical (search-replace + test).
- **`abuse_response` track's per-agent dashboards** — the Grafana panels will be keyed on `agent_id` from the audit decorator, which gets meaningful values only after Phase B wires real identity into the decorator.

## Shares primitives with

- **`defensive_perimeter`** — consumes Phase A's rate limiter + audit decorator; updates both with verified identity. Same Redis infrastructure. Same `audit_logs` Postgres table.
- **`intelligence_memory`** — the `verify_agent_token` function stays in place for back-compat. The new `resolve_identity` is a superset that *could* be used for the 3 KG read endpoints in a follow-up cleanup, but isn't part of v1.
- **`public_surface`** — public endpoints don't require identity by design, but the `GET /api/v1/identity/me` endpoint from this track returns anonymous-safe responses when no auth is present, so it can be linked from `FOR_AGENTS.md` without exposing anything sensitive.

## Architecture decisions worth knowing

1. **Pre-shared keys over JWT.** The dormant JWT path at `dependencies.py:87-114` was evaluated and deferred. Pre-shared keys are simpler to audit, faster to verify, and don't require JWKS infrastructure. JWT upgrade path is documented in spec §8.
2. **SHA256+salt over argon2id for v1.** Upgrade to argon2id is documented in spec §8 as a follow-up with a lazy-migration strategy. SHA256+salt is acceptable because tokens are 256-bit high-entropy values — brute-forcing is infeasible even without argon2.
3. **Scope pattern: `<action>:<resource>`.** Initial vocabulary in spec §3.C. Vocabulary expansion requires a spec update (enforced in CLAUDE.md "Ask first" per Task 8).
4. **Admin scope via the master key.** `STA_API_KEY` keeps full access through implicit `admin` scope, preserving all existing operator workflows.
5. **Attribution-only `verify_agent_token` stays.** Not deleted. Follow-up cleanup migrates the 3 KG read endpoints to `resolve_identity`; not blocking.

## Hard gate restated

Per the audit's recommended sequence: **this track closes the single biggest gate** for Moltbook publication. After `agent_identity` lands:

- ✅ Gate 1: `defensive_perimeter` (Phase A) — rate limiting, audit decorator, kill-switch protection. Landed (pending verification).
- ✅ Gate 2: `agent_identity` (Phase B) — this track.
- ⏳ Gate 3: `public_surface` implementation — specced, not yet started.
- ⏳ Gate 4: `moltbook_publisher` implementation — specced, not yet started.
- ⏳ Gate 5: 2-3 polished posts in `project-feed/` with `status: ready` — one draft exists.
- ⏳ Gate 6: Human Moltbook registration + Twitter verification.

**After Phase B, the path to the first Moltbook post is bounded, well-understood, and no longer blocked on any audit-critical finding.**

## Pointers

- Audit (full): `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- This track's spec: `conductor/tracks/agent_identity/spec.md`
- This track's plan: `conductor/tracks/agent_identity/plan.md`
- Sibling cross-refs: `conductor/tracks/defensive_perimeter/audit-cross-ref.md` (hard dependency), `conductor/tracks/intelligence_memory/audit-cross-ref.md` (Phase 4 foundation)
- Dormant JWT path: `trading/api/dependencies.py:87-114`
- Current attribution-only function: `trading/api/auth.py:37-53`
- Memory entries: `reference_agent_readiness_audit.md`, `project_mempalace_integration.md`, `feedback_parallel_opencode_stream.md`
