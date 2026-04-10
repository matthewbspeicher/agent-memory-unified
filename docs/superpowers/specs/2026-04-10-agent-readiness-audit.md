# Agent-Readiness Audit

**Date:** 2026-04-10
**Status:** Complete — read-only audit, no code changes
**Author:** Claude Code (synthesis on top of an Explore-subagent fact-gathering pass)
**Scope:** Trading API (`trading/`) and the internal agent runtime under `trading/agents/`
**Trigger:** User asked to "prep for a potential influx of agents" prior to integrating with Moltbook (the agent social network). This audit produces a current-state snapshot + gap analysis + recommended sequence so we know what we're committing to before any external-agent traffic arrives.

**Companion documents:**
- `docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md` — DESIGN.md token pipeline (already landed)
- `conductor/tracks/intelligence_memory/spec.md` — Gemini's v2 Intelligence/Memory spec (Phase 1 in flight at audit-write time)
- `conductor/tracks/intelligence_memory/plan.md` — Gemini's v2 implementation plan
- Memory: `reference_moltbook.md` — external context for the influx motivation

---

## 1. Executive summary

The trading API is **production-ready for human + single-tenant agent use** but is **not ready for an influx of external agents**. Three findings rise to critical, four to high, and three to medium. The single biggest gap is **no API rate limiting at all** — an external agent (or a leaked key) can hit any endpoint at line rate today, and there is nothing in the FastAPI middleware stack to push back.

The good news: most of the gaps are **infrastructure-level fixes** (middleware, dependency injection, structured logging) that don't require touching trading logic. The bad news: several dimensions (write surface, kill-switch, per-agent quotas) compound — fixing one without the others leaves a partial defense.

Three of the critical/high findings are already on Gemini's v2 Intelligence/Memory roadmap (per-agent identity, structured logging on writes, LLM budgets). Three are NOT on any active roadmap and are surfaced here for the first time (rate limiting, kill-switch protection, write-endpoint blast radius). The recommended sequence at the end of this document weaves both work streams together.

### Risk scoreboard

| # | Dimension | Risk | One-line gap |
|---|---|---|---|
| 1 | Identity & auth | 🟠 High | Single shared `X-API-Key`; no per-agent identity (dormant JWT path exists, unused) |
| 2 | Rate limiting | 🔴 **Critical** | **No API-level rate limiting whatsoever** |
| 3 | Agent-readable docs | 🟡 Medium | OpenAPI/Swagger publicly exposed (good); no `FOR_AGENTS.md` (gap) |
| 4 | Content to consume | 🟢 Low | Extensive ADRs / specs / plans / knowledge articles already exist |
| 5 | Interactive surfaces (write endpoints) | 🔴 **Critical** | ~40 write endpoints, including emergency `/risk/kill-switch` with no confirmation |
| 6 | Audit logs on writes | 🟠 High | `log_event()` framework exists; only ~5 production call sites; write endpoints emit nothing |
| 7 | Concurrency model | 🟡 Medium | Single asyncio event loop, `Semaphore(5)` cap; fine for current 13 agents, untested at higher load |
| 8 | Per-agent resource limits | 🔴 **Critical** | Zero per-agent quotas (no LLM budgets, no memory caps, no scan caps) |
| 9 | Observability | 🟡 Medium | OpenTelemetry + Prometheus + Sentry exist; structured event emission sparse |
| 10 | Inter-agent coordination | 🟡 Medium | In-memory SignalBus; no distributed locks; consensus opt-in (default `threshold=1`) |

---

## 2. Methodology

A research subagent (Explore type) was dispatched with a structured fact-gathering brief covering all 10 dimensions. The subagent's output was raw facts with file:line references — no recommendations, no prioritization. This document synthesizes those facts, adds risk scoring against an "external agent traffic via Moltbook" threat model, and produces a recommended sequence that interleaves with Gemini's already-running Intelligence/Memory v2 work.

**What this audit IS:** a current-state inventory + risk assessment + sequencing recommendation.
**What this audit IS NOT:** a spec for the fixes (each fix needs its own spec/plan if pursued), a security pen-test (no exploit attempts), or a coverage audit (test coverage is out of scope).

**Threat model assumed:** External AI agents discover this project via a Moltbook post, click through, hit `/openapi.json` to discover endpoints, then send requests under their own Moltbook identity OR with a leaked/shared API key. No assumption of malicious intent — just curious agents at scale, occasionally buggy, occasionally adversarial.

---

## 3. Dimension-by-dimension findings

### 3.1 Identity & auth — 🟠 High

**Current state.** A single shared `X-API-Key` header is enforced via `verify_api_key()` in `trading/api/auth.py:9-29`. The dependency uses `hmac.compare_digest()` for timing-safe comparison against `settings.api_key`, returns 401 on mismatch. All write routes and privileged reads inject this dependency (e.g., `trading/api/routes/competition.py:58`, `trading/api/routes/arena.py:9`, `trading/api/routes/orders.py:92`).

A **second auth path exists but is unused**: `get_current_user()` in `trading/api/dependencies.py:87-114` validates JWT bearer tokens or legacy `amc_*` tokens against Redis + DB via `shared.auth.validate.validate_token()`, returning `{sub, type, scopes}` for scope-based authorization (`require_scope("trading:execute")`). No active route consumes this dependency. It's either dead code or a planned future path.

**Per-agent identity.** None at the API level. The internal `trading/agents/` runtime has 13 named agents in `agents.yaml`, but their names are local concepts — they do not authenticate to the API. The only per-agent token concept is for memory access (`remembr.dev` agent tokens fetched in `trading/api/app.py:77-85`), and that's about which memory store the trading engine reads, not about who is calling the trading API.

**Frontend default.** `frontend/src/lib/api/factory.ts:12-14` reads `VITE_TRADING_API_KEY` and falls back to `'local-validator-dev'` in dev mode. CLAUDE.md confirms this is a valid dev key. **Misconfiguration risk:** if production deployment doesn't set `VITE_TRADING_API_KEY`, the frontend may either fall back to the dev key or silently fail.

**Risk:** 🟠 **High.** Single-key auth doesn't distinguish agents. There is no audit trail that says "agent X did Y at time Z" because all Xs are the same X. Under Moltbook traffic this becomes painful immediately — every observed action attributes to "the API key holder" and there's no way to revoke one agent without revoking all of them. Mitigated short-term by IP-based logging (if enabled) but that doesn't survive shared infrastructure.

**Mitigation already in flight:** Gemini's v2 spec section D includes *"Agent Identity: Transition from a shared `X-API-Key` to per-agent identifiers for KG read/write auditing."* This is scoped to KG operations but the same mechanism can extend to all routes. The dormant JWT path in `dependencies.py` is the natural foundation.

---

### 3.2 Rate limiting — 🔴 Critical

**Current state.** **None.** A grep across the entire `trading/` tree for `slowapi`, `limiter`, `rate_limit`, `RateLimit`, or `throttle` (in the API middleware sense) returns zero hits. The `BrokerError.RateLimitExceeded` handler in `trading/api/startup/error_handlers.py:44-46` exists but is for **downstream broker** rate limits (IBKR, Alpaca) bubbling up to the client — it does not enforce limits on incoming requests.

The agent runtime has a `Semaphore(max_concurrent_scans=5)` in `trading/agents/runner.py:120`, which caps internal scan concurrency, not external API request rate.

**Risk:** 🔴 **Critical.** This is the single most impactful gap in the audit. A single misconfigured external agent, or a leaked API key, can hit any endpoint at line rate. There is no per-IP throttle, no per-key throttle, no global ceiling. Under Moltbook scale (1.5M+ agents in the population, even 0.01% adoption is 150 agents), an unintentional polling loop can trivially saturate the trading engine.

The compounding factor: many of the writable endpoints (`/api/v1/agents/{name}/scan`, `/api/v1/tuning/.../grid-search`, `/api/v1/agents/{name}/evolve`) trigger expensive downstream operations (LLM calls, database writes, broker queries). Each request is cheap; each request *fanout* is not.

**Mitigation:** Not in any active spec. **This audit recommends adding rate limiting before any external agent traffic arrives** — see §5 sequencing.

**Recommended approach:** `slowapi` (FastAPI-native, Redis-backed sliding window) with three tiers:
- Anonymous (no auth header): 10 req/min, read-only endpoints only
- Verified Moltbook identity: 60 req/min, read + low-risk writes
- Registered (per-agent key): 300 req/min, scope-gated full surface

---

### 3.3 Agent-readable docs — 🟡 Medium

**Current state.** FastAPI's default docs are exposed. `trading/api/app.py:2010` constructs `FastAPI()` without overriding `docs_url`, `redoc_url`, or `openapi_url`, so the standard endpoints are live:
- `/docs` → Swagger UI
- `/redoc` → ReDoc
- `/openapi.json` → machine-readable spec

All three are publicly accessible — no auth requirement on the docs endpoints themselves. Whether this is a feature or a leak depends on whether you want endpoint discovery to be free.

**Agent-specific files.** None. No `FOR_AGENTS.md`, `AGENTS.md`, `agents.txt`, or `/.well-known/agents` file at the repo root or `frontend/public/`. The `.claude/knowledge/AGENTS.md` exists but documents the *internal* knowledge compiler agent framework, not external-agent onboarding.

**Risk:** 🟡 **Medium.** OpenAPI exposure is actually *good* for an agent-facing API — it's the single most agent-consumable artifact we have. The gap is the absence of a curated entry point: an arriving agent gets dropped at the FastAPI Swagger UI with no indication of *which* endpoints are meant for them, *how* to authenticate, *what* the rate limits are, or *where* to file abuse complaints.

**Recommended approach:** A single `FOR_AGENTS.md` at the repo root + a `/.well-known/agents.json` static file served by Vite + linked from `/openapi.json` description field. ~1 hour of work, very high information density per byte.

---

### 3.4 Content to consume — 🟢 Low

**Current state.** Substantial. Inventoried by the subagent:

| Source | Count | Path |
|---|---|---|
| ADRs | 9 | `docs/adr/` |
| Superpowers specs | 22 | `docs/superpowers/specs/` |
| Superpowers plans | 46 | `docs/superpowers/plans/` |
| Knowledge articles | (multiple) | `.claude/knowledge/articles/concepts/`, `.claude/knowledge/articles/connections/` |
| Daily knowledge logs | (rolling) | `.claude/knowledge/daily/` |
| Design docs | 3 | `docs/DESIGN.md`, `docs/DESIGN-TRADING.md`, `frontend/design/DESIGN.md` |
| Total markdown in `docs/` | ~97 files | — |

**Risk:** 🟢 **Low.** The content surface is rich and growing. The gap isn't *content*, it's *discoverability* — see dimension #3. Once there's a `FOR_AGENTS.md` index pointing into this corpus, agents have plenty to consume.

**One related observation:** The `.claude/knowledge/` corpus is auto-generated from Claude Code session captures (per `project_kb_bootstrap` memory). It's not currently exposed via any HTTP endpoint — if we want external agents to consume it, we need either a static-file serve or a `/api/v1/knowledge/articles/{slug}` route. Not urgent, but flag it.

---

### 3.5 Interactive surfaces (write endpoints) — 🔴 Critical

**Current state.** ~40 write endpoints (POST/PUT/PATCH/DELETE) across the trading API. Full inventory in the subagent's raw report; key categories:

| Domain | Count | Sensitivity |
|---|---|---|
| Arena (sessions, turns, claim-rewards) | 3 | Medium — gameplay state |
| Competition / Gladiators (loadout, matches, bets, settle, breed) | 6 | Medium-High — economic state |
| Orders / Trades | 4 | **High — real money** |
| Risk (kill-switch, rules) | 2 | **Critical — system halt** |
| Agents (create, sync, start/stop, scan, evolve, tokens) | 8 | High — agent runtime control |
| Memory / Learning (tune, transition, trust, overrides) | 4 | Medium-High — training state |
| Tuning (evolution, cycle, grid-search, genetic-optimize) | 4 | Medium — expensive LLM ops |
| Backtest / Sandbox / Strategy health overrides | 5 | Medium |
| Opportunities (approve, reject, exec) | 5 | High — money via opportunity execution |
| Experiments / Tournament / Brief / Journal / Shadow / Copilot / Achievements / Imports | ~6 | Mixed |

**The kill-switch.** `POST /api/v1/risk/kill-switch` (`trading/api/routes/risk.py:28`) halts all trading. **No confirmation, no rate limit, no 2FA-equivalent, no cooldown.** A single API call with the shared key disables the engine. Audit log emission unclear (see §3.6).

**Trade execution.** `POST /api/v1/orders` and `POST /api/v1/trades` create real broker orders. Auth-gated by the shared key — no per-agent scopes, no order-size caps independent of the agent runtime.

**Agent control.** `POST /api/v1/agents/{name}/start`, `/stop`, `/scan`, `/evolve` give the caller full lifecycle control over any of the 13 internal agents. Combined with `PATCH /api/v1/agents/{name}` (config update) and `PUT /api/v1/agents/{name}/remembr-token` (memory token rotation), the API holder can fully reconfigure an agent's behavior at runtime.

**Risk:** 🔴 **Critical.** The blast radius of a leaked or exposed `STA_API_KEY` is the *entire trading system*: trades, agent control, risk halt, competition state, memory state. Today this is acceptable because the key holder is the operator. Under Moltbook traffic, three changes happen: (a) more traffic from more sources increases leak probability, (b) external agent identities want different scopes than "everything," and (c) any single misbehaving agent or compromised key escalates to "stops the trading engine" or "drains the portfolio" trivially.

**Mitigations to consider (in priority order):**
1. **Per-endpoint scope tags** in the auth dependency (e.g., `require_scope("orders:write")`, `require_scope("risk:halt")`). The dormant JWT path in `dependencies.py` already supports scopes — wire it in.
2. **Confirmation tokens for destructive endpoints** (kill-switch, agent stop, mass cancel). Two-call pattern: `POST /risk/kill-switch/initiate` → returns `{token, expires_in: 60}` → `POST /risk/kill-switch/confirm` with the token. Doesn't help if the attacker has the key but does prevent accidental triggers.
3. **Rate limit destructive endpoints separately** (1 req/hour for kill-switch, etc.).
4. **Read-only mode for unverified agents** by default, unlocking writes only after explicit per-agent registration.
5. **Audit log every write** (see §3.6).

---

### 3.6 Audit logs on writes — 🟠 High

**Current state.** The structured-logging framework exists at `trading/utils/logging.py:73-99` with `log_event(logger, level, event_type, msg, data={...})`, two formatters (`JSONFormatter`, `StructuredTextFormatter`), and the convention documented in CLAUDE.md and ADR-0008. CLAUDE.md lists six event types: `signal.received`, `signal.consensus`, `trade.decision`, `trade.executed`, `bridge.poll`, `bridge.signal`, `error`.

**Actual usage in production code: ~5 call sites total.**
- `trading/data/signal_bus.py:26` — `signal.received`
- `trading/intelligence/layer.py:129,138` — two intelligence layer events
- (a few others in tests / CLI tools)

**The other defined event types are not emitted anywhere.** `trade.decision`, `trade.executed`, `bridge.poll`, `bridge.signal`, `error` — all documented, none called. Write endpoints (orders, agents, risk, competition) do not emit structured events on success or failure. Standard Python logging captures HTTP requests and errors but with no consistent `event_type` tagging, making post-hoc forensic queries painful.

**Risk:** 🟠 **High.** If a leaked key is used to drain the portfolio, the only forensic trail is whatever the standard application logs captured at the time. There is no `audit_log` table, no per-request structured event with `agent_id + action + result`, no append-only ledger. The framework to add this is sitting right there — it's just not wired in.

**Mitigations already in flight:** Gemini's v2 spec section D states *"Every memory write, KG update, and context generation MUST emit a structured event ... via `trading/utils/logging.py`."* This is great for the *new* code Gemini is writing. It does NOT retroactively instrument the *existing* ~40 write endpoints.

**Recommended:** Adopt the same "MUST emit" rule for all existing write routes. Likely a 1-2 day instrumentation pass: add a `@audit_event("orders.created")` decorator (or middleware) that wraps each write route and emits a structured log on entry + exit + error. The decorator can be one shared piece of code.

---

### 3.7 Concurrency model of internal agents — 🟡 Medium

**Current state.** AsyncIO-based, single event loop. From `trading/agents/runner.py`:

- `import asyncio` (line 3)
- `self._tasks: dict[str, asyncio.Task]` — one task per agent (line 80-121)
- `self._scan_semaphore = asyncio.Semaphore(max_concurrent_scans)` — default `5` (line 120)
- `self._poll_task: asyncio.Task | None = None` — registry-poll task (line 121)
- `_execute_scan()` acquires the semaphore before running `agent.scan()` (line 257+)
- Per-scan timeout via `asyncio.wait_for(scan, timeout)` (line 383-386)
- Graceful drain via `asyncio.Event()` per agent on stop (lines 468-493)
- Continuous agents: `asyncio.create_task(self._run_continuous(agent))` (line 210)
- Cron agents: `asyncio.create_task(self._run_cron(agent))` (line 213)

All 13 agents share **one Python event loop**. CPU-bound work in any agent blocks others. The semaphore caps concurrent scans at 5 — if all 13 agents wake at once, 8 of them queue.

**Risk:** 🟡 **Medium.** Adequate for current scale. Risks emerge if: (a) scan count grows past ~30 agents and the semaphore=5 cap creates pathological queueing, (b) any agent does meaningful CPU work (vector ops, regex over large text, etc.) and blocks the loop, (c) external traffic (Moltbook visitors) triggers additional `/agents/{name}/scan` requests that contend for the same semaphore.

**Mitigations:** Most likely sufficient at current scale. Worth instrumenting (`scan_queue_depth`, `scan_semaphore_wait_time`) to know when the cap becomes a bottleneck. Worth raising to a larger number (`max_concurrent_scans=20`?) if scaling to more agents.

---

### 3.8 Per-agent resource limits — 🔴 Critical

**Current state.** **Zero per-agent quotas.** The subagent verified `trading/agents/config.py` and `agents.yaml`:
- `scan_timeout: float = Field(default=120.0, ge=1.0, le=600.0)` — per-scan max wall time
- Strategy-specific knobs (`max_markets_per_scan: 30`, `max_iterations: 5`) — these are *parameters*, not *quotas*

There are **no LLM call budgets**, no per-agent token quotas, no monthly cost ceilings, no memory caps, no DB write limits. An agent can spawn unlimited scans, write unlimited opportunities, trigger unlimited tuning cycles. The only protection is the global `Semaphore(5)` (see §3.7) which limits *concurrency*, not *consumption*.

**Risk:** 🔴 **Critical.** Two compounding scenarios:
1. **Internal misconfiguration:** A new agent or a tuning bug runs an unbounded loop calling LLMs. Cost runs up before anyone notices. No circuit breaker.
2. **External agent traffic triggering internal work:** If Moltbook visitors can hit `/api/v1/agents/{name}/scan` or `/api/v1/tuning/{agent_name}/grid-search`, they're effectively spending the operator's LLM budget on the operator's API key. The audit calls this out specifically because grid-search and genetic-optimize are inherently expensive operations that fan out to many LLM calls per request.

**Mitigations already in flight:** Gemini's v2 spec section D includes *"LLM Budgeting: Implement `max_calls_per_scan` and `monthly_token_quota` in `agents.yaml`."* This is exactly the right shape — it just needs to be enforced at the call site, not just declared in config. The enforcement point is most likely in `trading/llm/client.py` (a thin counter wrapper around the Anthropic client) or in `trading/agents/base.py` (wrap the agent's LLM calls in a quota check).

---

### 3.9 Observability — 🟡 Medium

**Current state.** Three observability surfaces exist:
1. **OpenTelemetry traces.** Used in `runner.py` and `router.py` (e.g., `tracer.start_as_current_span("agent_scan")`). Real spans, real telemetry.
2. **Prometheus metrics.** Exposed at `/metrics` via `prometheus_fastapi_instrumentator`. Gated behind `verify_api_key`.
3. **Sentry error tracking.** Wired in `app.py:2043-2057` if `SENTRY_DSN` is set.

The structured `log_event()` framework exists (see §3.6) but is sparsely used.

**Risk:** 🟡 **Medium.** The infrastructure is in place; the gap is *consistent emission*. Missing pieces specifically for the agent influx scenario:
- No agent-centric dashboard ("show me everything `agent-foo` did in the last hour")
- No request-level tracing tied to a caller identity (no per-agent request IDs in the spans)
- No alerting on suspicious patterns (kill-switch invocation, mass orders, rapid tuning loops)

**Mitigations:** Mostly orthogonal to the audit findings. Worth tracking but not critical pre-Moltbook.

---

### 3.10 Inter-agent coordination — 🟡 Medium

**Current state.** Five mechanisms identified:

1. **SignalBus** (`trading/data/signal_bus.py:12-64`) — in-memory async pub/sub. Signals pruned on age (TTL), capped at 1000 recent. **Not distributed** — process restart loses all signals.
2. **DataBus** (`trading/data/bus.py:40+`) — TTL-cached market data, in-memory.
3. **OpportunityRouter** (`trading/agents/router.py:54+`) — hub-and-spoke; agents → router → broker. No agent-to-agent messaging.
4. **ConsensusRouter** (`trading/agents/router.py:1450+`) — wraps OpportunityRouter, requires N-of-M agent agreement. Default `consensus_threshold=1` per `trading/config.py:239-240` — i.e., **consensus is opt-in and disabled by default**, any single agent can trigger a trade.
5. **EventBus** — Redis-backed event publication, used for real-time notifications. Wired in `app.py`.

**Duplicate-action prevention:** None at the data layer. The router processes opportunities sequentially, but if two agents create opportunities for the same symbol in the same cycle, both are routed independently. Whether they both execute depends on broker state, not on a coordination mechanism.

**Risk:** 🟡 **Medium.** The current setup is fine for cooperative agents that the operator controls. Three concerns under external traffic:
- In-memory SignalBus means any agent insight from external traffic dies on restart
- No distributed locks → if we ever scale to multiple trading-engine processes, race conditions
- Consensus-disabled-by-default means any one agent (internal or, post-rate-limiting, external) can drive trades unilaterally

**Mitigations:** Defaults are conservative enough for now. Worth raising `consensus_threshold` to 2+ before opening write endpoints to external agents. Long-term, consider Redis-backed SignalBus for restart-survivable signal history.

---

## 4. Cross-references to Gemini's Intelligence/Memory v2 spec

The two work streams (this audit and Gemini's v2 plan) overlap meaningfully. Mapping the audit findings to Gemini's roadmap:

| Audit dimension | Gemini v2 coverage | Gap remaining |
|---|---|---|
| #1 Identity & auth | ✅ "Agent Identity" guardrail (D) — scoped to KG ops | Need to extend per-agent identity to *all* routes, not just KG |
| #2 Rate limiting | ❌ Not addressed | **Separate work stream needed** |
| #3 Agent docs | ❌ Not addressed | `FOR_AGENTS.md` is its own ~1 hour task |
| #4 Content | n/a | n/a |
| #5 Write surface / kill-switch | ❌ Not addressed | **Separate work stream needed** |
| #6 Audit logs | ✅ "Structured Logging" guardrail (D) — for new write paths | Need retroactive instrumentation pass on existing ~40 write endpoints |
| #7 Concurrency | ❌ Not addressed | Adequate for now; monitor |
| #8 Per-agent resource limits | ✅ "LLM Budgeting" guardrail (D) — `max_calls_per_scan`, `monthly_token_quota` | Enforcement point needs to be wired into `trading/llm/client.py` or `trading/agents/base.py` |
| #9 Observability | ❌ Not addressed | Adequate for now; monitor |
| #10 Inter-agent coordination | ❌ Not addressed | Defaults conservative; revisit before write surface opens to external agents |

**Reading:** Gemini's plan addresses 3 of the 4 high-priority audit findings (#1, #6, #8) at the right architectural level, but those addresses are scoped to *new* code (the KG, the L0/L1 context, the ReACT agent). They do not retroactively fix the *existing* surface. Three critical findings (#2 rate limiting, #5 write surface protection, kill-switch confirmation) are not on Gemini's roadmap at all and need their own work stream.

**Net reading: Gemini is doing the right things in the right order for the memory-and-intelligence axis. The agent-readiness axis is largely uncovered and is what this audit is for.**

---

## 5. Recommended sequence

A four-phase sequence interleaving Gemini's v2 work with audit-driven hardening. Each phase is independent enough to ship as its own PR. Order minimizes blast radius before opening any external surface.

### Phase 0 — Already in flight (Gemini)

- Gemini Phase 1 Task 1: WAL + busy_timeout in `LocalMemoryStore.connect()`
- Gemini Phase 1 Task 2: Content-hash dedup with `access_count` increment
- *Coordination note:* incorporate audit-finding #6 by emitting `memory.deduplicated` and `memory.stored` structured events on every write

**Gate:** None — already executing.

### Phase A — Defensive perimeter (audit-driven, 1-2 days)

Land the minimum viable rate-limiting + audit-log baseline before any external agent traffic is invited.

1. **Add `slowapi` middleware** with three tiers (anon / verified / registered). Default-deny for unknown identity → 10 req/min anon. Wire to existing Redis instance for distributed counters.
2. **Add `@audit_event(action_name)` decorator** for write routes. Wraps the route to emit `log_event()` on entry, success, and failure with `data={method, path, status, agent_id?, request_id, duration_ms}`.
3. **Apply the decorator** to the highest-risk routes first: `risk.py` (kill-switch + rules), `orders.py`, `trades.py`, `agents.py` (start/stop/evolve), `competition.py` (settle, breed). Other routes can be backfilled in a follow-up.
4. **Two-step confirmation** for `/risk/kill-switch`: split into `/initiate` (returns 60s token) + `/confirm` (consumes token). Optional but recommended.

**Cross-stream impact:** Phase A's `@audit_event` decorator becomes the canonical primitive Gemini's v2 plan can reuse for its KG/memory write events.

**Gate:** None of Phase A blocks Gemini Phase 1. They can run in parallel.

### Phase B — Identity layer (audit + Gemini, 2-3 days)

Land per-agent identity using the dormant JWT path in `trading/api/dependencies.py`.

1. **Wire `get_current_user()` into a new `verify_agent_or_apikey()` dependency** that accepts EITHER the legacy `X-API-Key` (back-compat) OR a per-agent JWT bearer token.
2. **Implement per-agent registration** at `/api/v1/agents/identity/register` returning a scoped JWT.
3. **Define scopes** as `<resource>:<action>` (e.g., `arena:read`, `arena:participate`, `orders:write`, `risk:halt`). Scope `*` is admin.
4. **Migrate the highest-risk routes** from `verify_api_key` to `require_scope(...)`. Continue accepting the legacy API key as a master scope `*` for back-compat.

**Cross-stream impact:** Gemini's Phase 2 KG endpoints can use this identity layer from day one rather than re-inventing it.

**Gate:** Phase A landed (rate limiting must be in place before per-agent registration goes live, or anyone can register infinite agents).

### Phase C — Gemini's Intelligence/Memory Phase 2-3 (1-2 weeks)

Gemini executes its v2 Phases 2 (KG core + integration) and 3 (L0/L1 context + ReACT agent) per the v2 plan.

**Cross-stream impact:** Phase C's KG endpoints are gated by Phase B's identity layer. Phase C's structured logging is the same pattern as Phase A's `@audit_event`. Phase C's LLM budget enforcement closes audit finding #8.

**Gate:** Phase B landed (KG read endpoints need per-agent identity for read-attribution).

### Phase D — External agent surface (audit-driven + Moltbook integration, 1 week)

Open a curated subset of the API to external agents.

1. **`FOR_AGENTS.md` at the repo root** + `/.well-known/agents.json` static file.
2. **Read-only KG and memory query endpoints** for unverified Moltbook-identified agents.
3. **Arena participation endpoints** for verified agents (place bets, view leaderboard) — gated behind `arena:participate` scope.
4. **The Moltbook three-layer integration** from `reference_moltbook.md` (`project-feed/` directory + publisher script).
5. **First Moltbook post** announcing the project's existence + capabilities + abuse-contact.

**Gate:** Phases A, B, C all landed. **Do not invite external agents before rate limiting + identity + structured logging are all live.**

### Phase E — Hardening + observability (open-ended)

Backfill items not in Phases A-D:
- Audit-log instrumentation on the remaining write routes (~30 endpoints)
- Per-agent observability dashboard (Grafana panel keyed on `agent_id`)
- Raise `consensus_threshold` to 2+ once multiple agents share the system
- Redis-backed SignalBus for restart-survivable history
- Quota enforcement at `trading/llm/client.py` if Gemini's enforcement point lands elsewhere

---

## 6. Risks not in the dimension table

A few issues the subagent surfaced that don't fit cleanly into the 10 dimensions but are worth flagging:

1. **Hybrid auth path is dead code.** `get_current_user()` and the JWT validation logic in `trading/api/dependencies.py:87-114` exist but no route consumes them. Either this is planned-but-stalled work (resurrect) or true dead code (delete or document). Phase B's plan resurrects it.

2. **Default dev API key in frontend.** `VITE_TRADING_API_KEY` falls back to `'local-validator-dev'`. This is fine for dev but a misconfiguration risk in production. Worth a runtime check that fails the frontend build if the env var isn't set.

3. **`/openapi.json` exposes everything.** Including the kill-switch, the agent control surface, the breed/settle endpoints. This is *intentional* — we want agents to discover the API — but it means the endpoint inventory is public. If we add admin-only routes later, they need explicit `include_in_schema=False` or a separate `FastAPI()` mount.

4. **`portfolio.py` is read-only.** Good. No write endpoints found. All trading goes through the orders/trades surface. Worth preserving — don't add portfolio-level write endpoints under pressure to "let agents rebalance directly."

5. **`shadow.py` has a `/promote` endpoint.** `POST /api/v1/shadow/agents/{agent_name}/promote` graduates a shadow-mode agent to live trading. This is a high-trust action that should be in scope `agents:promote` or admin-only when scopes are introduced.

---

## 7. What this audit deliberately does NOT cover

- **Test coverage** — orthogonal concern, separate audit if needed.
- **Performance / load testing** — no synthetic load was generated.
- **Pen testing / exploit attempts** — purely a code-read audit, no payloads sent.
- **Frontend security** — only mentioned in passing for the `VITE_TRADING_API_KEY` default. The frontend has its own threat model (XSS, CSRF, etc.) that needs its own audit.
- **Secrets management** — `.env` file handling, key rotation policy, etc. CLAUDE.md has working boundaries on this; assumed in-scope of those boundaries.
- **Database security** — Postgres connection auth, RLS policies, backup encryption. Worth its own pass.
- **The frontend's "two visual sub-identities"** finding from `reference_frontend_dual_identity.md` — that's a UX/branding concern, not an agent-readiness concern.
- **Bittensor wallet protection** — covered by CLAUDE.md "Ask first" boundaries; assumed adequate.

---

## 8. Recommended next actions

**For the operator (mspeicher):**

1. **Read this audit. Confirm or push back on the risk scoring** — particularly the three 🔴 Critical findings. They drive the sequencing.
2. **Decide whether to commit to Phases A → B → D as separate spec/plan workstreams** or combine into one. If separate, each gets its own brainstorming → spec → plan flow. If combined, one larger spec.
3. **Coordinate with Gemini** — Gemini's v2 plan complements this audit but the two streams need to know about each other. Either share this audit doc with Gemini or have me publish a short companion at `conductor/tracks/intelligence_memory/audit-cross-ref.md` that Gemini's stream can reference.
4. **Decide whether to land any of Phase A *before* the first Moltbook post**. The audit's strong recommendation is yes — rate limiting at minimum.

**For me (next session continuity):**

1. If asked to spec Phase A: invoke brainstorming → spec → plan flow with the rate-limiting + audit-log decorator scope.
2. If asked to spec Phase B: same flow with the per-agent identity scope, building on the dormant JWT path.
3. If asked to spec Phase D: same flow tied to the existing Moltbook integration plan in `reference_moltbook.md`.
4. **Do not begin any of these without explicit user authorization.** This audit is read-only; the next phase requires a sign-off.

---

## 9. Appendix: subagent fact-gathering snapshot

The full raw subagent report is preserved in conversation history. Key file:line references inlined in §3 above. If a future session needs to re-run the audit, the same Explore-subagent brief (10 dimensions, fact-only, no recommendations) can be re-used; expected output should match this document's §3 within ~10% structural variance.

**Audit-write snapshot:** as of 2026-04-10, HEAD of `main` is at `bb8a4ff` (the last token-pipeline polish commit) with Gemini's Phase 1 Task 1 in flight. If significant time has passed and this audit is being read in a much later session, re-verify the dimensions before acting on the recommended sequence — particularly #1 (auth), #2 (rate limiting), and #6 (audit logs), which are the most likely to have moved.
