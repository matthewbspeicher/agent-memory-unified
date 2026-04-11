# Cross-reference: Agent-Readiness Audit ↔ Public Surface

**Created:** 2026-04-10
**By:** Claude Code
**Purpose:** Map this track's scope to the agent-readiness audit findings. Same pattern as `conductor/tracks/defensive_perimeter/audit-cross-ref.md` and `conductor/tracks/intelligence_memory/audit-cross-ref.md`.

## Track identity

This is the **second track created specifically to close audit findings** (the first being `defensive_perimeter`). It lands the agent-facing public surface (`FOR_AGENTS.md`, `/.well-known/agents.json`, landing route, curated read-only endpoints) that constitutes the user-visible portion of audit Phase D prep.

Important distinction: this track is **"Phase D prep,"** not Phase D itself. Phase D (actually inviting external agent traffic) requires this + `defensive_perimeter` + `agent_identity` all landed before the Moltbook first-post goes out. This track ships the *surface*; the *gate* remains closed until the other pieces land.

## Audit findings this track targets

| Audit dimension | Risk | Coverage |
|---|---|---|
| 🟡 #3 Agent-readable docs | Medium | **Closes** — `FOR_AGENTS.md` at repo root is the curated entry point. `agents.json` provides the machine-readable manifest. Landing route on the trading API (`GET /`) replaces the current 404 with a JSON welcome pointing at all of the above. |
| 🟢 #4 Content to consume | Low | **Extends** — The existing corpus (ADRs, specs, plans, `.claude/knowledge/`) is already adequate per the audit; this track makes it *discoverable* via `FOR_AGENTS.md` links and the `/engine/v1/public/milestones` endpoint that reads the `project-feed/` directory. |

## Audit findings this track consumes (but doesn't own)

| Audit dimension | Coverage by | What this track uses |
|---|---|---|
| 🔴 #2 Rate limiting | `defensive_perimeter` | Anonymous tier (10 req/min per IP) applied to all public endpoints. Hard dependency — this track's Phase 3 (routes/public.py) cannot safely merge before defensive_perimeter lands. |
| 🟠 #1 Identity & auth | `intelligence_memory` Phase 4 foundation + future `agent_identity` track | Public endpoints explicitly do NOT require identity (anonymous-allowed). The `agents.json` manifest describes the three tiers honestly, and `FOR_AGENTS.md` links to the `verify_agent_token` / `verify_api_key` headers for agents wanting to move to authenticated tiers. |
| 🟠 #6 Audit logs on writes | `defensive_perimeter` | Public endpoints are read-only (enforced by the scoping linter in Task 5) — no write-side audit logging needed here. |

## Audit findings this track explicitly does NOT address

| Audit dimension | Risk | Why out of scope |
|---|---|---|
| 🔴 #5 Write surface protection / kill-switch | Critical | This track is **read-only by design**. The scoping linter (Task 5) enforces that `routes/public.py` cannot call any mutation method. Write protection remains `defensive_perimeter` territory. |
| 🔴 #8 Per-agent resource limits (cross-cutting) | Critical | Per-scan enforcement lives in `intelligence_memory` (agent LLM budgets). Global cost ceilings are out of scope for this track. |
| 🟡 #7 Concurrency model | Medium | Adequate for current scale; unchanged by public surface. |
| 🟡 #9 Observability | Medium | Separate track (`abuse_response`) owns per-agent Grafana dashboards. This track's endpoints inherit the existing OpenTelemetry traces + Prometheus metrics from `defensive_perimeter`. |
| 🟡 #10 Inter-agent coordination | Medium | Internal concern; public surface doesn't expose coordination primitives. |

## Dependencies

### Hard dependencies (must land before this track merges)

- **`defensive_perimeter` (audit Phase A)** — for the anonymous rate limit tier. Specifically, the middleware, the tier routing, and the `include_in_schema=False` discipline on privileged routes. Without this, public endpoints are unrate-limited and the KG / milestone endpoints become trivial DoS vectors.

### Soft dependencies (desired but not strictly required)

- **`intelligence_memory` track's KG** — `/engine/v1/public/kg/entity/{name}` and `/engine/v1/public/kg/timeline` assume `query_entity_public` and `timeline_public` methods on the KG. If those methods don't exist yet, the endpoints gracefully return empty responses. A small follow-up adds a `public: bool` column or an allowlist filter.
- **`moltbook_publisher` track** — `/engine/v1/public/milestones` reads `project-feed/*.md` files with `status: posted`. Until the publisher runs at least once, this endpoint returns an empty list with a `note: "No milestones published yet"` message. The dependency is soft: the endpoint is functional (empty list) from day one.

## Unblocks

- **Audit Phase D (external agent traffic invitation)** — this track ships the surface agents will hit. Combined with `defensive_perimeter` (Phase A) and `agent_identity` (Phase B), Phase D becomes gated only on content, operational readiness, and the human Moltbook registration step.
- **`moltbook_publisher` track** — the `GET /engine/v1/public/milestones` endpoint is the consumer side of the publisher's write path. The two tracks can be developed independently but are designed to work together.
- **First Moltbook post** — once this track + `defensive_perimeter` + `agent_identity` + the publisher all land, the only remaining blockers are the content polish and the human Moltbook registration. The surface is ready for strangers the moment this track merges (assuming dependencies met).

## Shares primitives with

- **`defensive_perimeter`** — consumes the anonymous rate limit tier, the `include_in_schema=False` discipline, and (optionally) the `@audit_event` decorator for instrumenting public endpoint access even though they're read-only. Read-side instrumentation is useful for abuse detection.
- **`moltbook_publisher`** — both tracks touch `project-feed/`. This track reads it (via the milestones endpoint); the publisher writes to it (post UUIDs back into frontmatter).
- **`intelligence_memory`** — the `query_entity_public` and `timeline_public` methods on the KG are the interface. They can be added as a small enhancement to the existing KG code without a full new spec.

## Hard gate restated

Per the audit's recommended sequence and the `reference_project_feed_convention.md` memory entry: **do not invite external agent traffic** (no Moltbook posts announcing the project, no submission of `/.well-known/agents.json` to aggregator indexes, no links in the project README that point external eyes at the API) **until**:

1. `defensive_perimeter` (Phase A) landed — rate limiting, audit decorator, kill-switch protection ✗
2. `agent_identity` (Phase B) landed — real per-agent authentication ✗ (not yet specced)
3. `public_surface` (this track) landed ✗
4. `moltbook_publisher` landed ✗
5. 2-3 polished posts in `project-feed/` with `status: ready` ✗
6. Human: Moltbook agent registration + Twitter verification (one-time) ✗

This track represents progress on gate #3. It does not open the door; it installs the door.

## Pointers

- Audit (full): `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- This track's spec: `conductor/tracks/public_surface/spec.md`
- This track's plan: `conductor/tracks/public_surface/plan.md`
- Sibling cross-refs: `conductor/tracks/defensive_perimeter/audit-cross-ref.md`, `conductor/tracks/intelligence_memory/audit-cross-ref.md`
- Project-feed convention: `reference_project_feed_convention.md`
- Moltbook reference: `reference_moltbook.md`
