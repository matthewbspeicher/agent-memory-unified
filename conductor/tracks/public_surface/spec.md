# Specification: Public Surface (Audit Phase D prep)

## 1. Objective

Create the curated, safe-by-default read-only surface that arriving external agents (via Moltbook or any other discovery path) encounter first. Today they'd hit either a 404 or the raw FastAPI Swagger UI — neither communicates intent, scope, rate limits, or abuse-reporting channels. This track lands the agent-facing entry points: `FOR_AGENTS.md`, `/.well-known/agents.json`, a landing route on the trading API, and a namespaced `trading/api/routes/public.py` with curated read-only endpoints gated behind the anonymous rate limit tier from the `defensive_perimeter` track.

This is **audit Phase D prep**, not Phase D itself. Phase D (external agent traffic actually arriving) requires this track + `defensive_perimeter` (rate limiting) + `agent_identity` (real per-agent auth) all landed before the Moltbook first-post can go out. This track ships the *surface*; the *gate* remains closed until the other pieces land.

## 2. Non-goals

- **Write endpoints for external agents** — participation, betting, signal submission. Those are Phase D proper, gated on `agent_identity` landing.
- **Moltbook-specific routing or identity handling** — the surface is discovery-agnostic. Any agent (Moltbook, direct curl, another platform) sees the same thing.
- **Full internationalization of FOR_AGENTS.md** — English only for v1.
- **Replacing `CLAUDE.md` or the existing `docs/`** — this is agent-onboarding, not developer docs.
- **Rate limiting itself** — consumed from `defensive_perimeter` (Phase A). This track assumes the `slowapi` middleware exists and routes public endpoints through the anonymous tier.

## 3. Architecture & Design

### A. Directory layout

```
frontend/                              (unchanged)
├── public/
│   └── .well-known/                   # NEW — static files served by Vite
│       └── agents.json                # NEW — machine-readable manifest
trading/
├── api/
│   ├── routes/
│   │   └── public.py                  # NEW — curated read-only router
│   └── landing.py                     # NEW — GET / handler returning JSON welcome
└── public_content/                    # NEW — static files (FOR_AGENTS.md copy, etc.)
    ├── FOR_AGENTS.md
    └── agents.json                    # canonical source; frontend copy is a symlink or duplicate
FOR_AGENTS.md                          # NEW — repo root, human-readable
TERMS_FOR_AGENTS.md                    # NEW — short ToS covering abuse / data use / rate limits
```

**Canonical source of `agents.json`:** `trading/public_content/agents.json`. Served at:
- `GET https://<host>/.well-known/agents.json` (via frontend Vite static + FastAPI fallback)
- `GET https://<api-host>/engine/v1/public/agents.json` (FastAPI direct)

Both routes return identical content — the FastAPI route is the fallback when the frontend isn't serving.

### B. Public router (`trading/api/routes/public.py`)

A new FastAPI router mounted at `/engine/v1/public/` with the following endpoints:

| Path | Purpose | Payload shape |
|---|---|---|
| `GET /engine/v1/public/status` | Project liveness + version + uptime | `{name, version, uptime_seconds, served_by, docs}` |
| `GET /engine/v1/public/agents` | List of this project's internal agents (name, strategy, one-line description) — no internal IDs, no secrets | `{agents: [{name, strategy, description, action_level}], docs}` |
| `GET /engine/v1/public/arena/state` | Current arena state: active match (if any), current season, leaderboard top 5 | `{current_match, season, top_leaderboard, docs}` |
| `GET /engine/v1/public/leaderboard` | Full public leaderboard — agent names, ranks, Elo, last 10 match outcomes | `{leaderboard: [...], as_of, docs}` |
| `GET /engine/v1/public/kg/entity/{name}` | Read-only KG query for a named entity — facts, relationships, confidence scores. Does NOT expose internal agent memory, only graph triples. | `{entity, facts: [...], count, docs}` |
| `GET /engine/v1/public/kg/timeline` | Temporal KG timeline for an entity | `{entity, timeline: [...], count, docs}` |
| `GET /engine/v1/public/milestones` | Recent published project-feed entries (after the publisher exists) | `{milestones: [...], docs}` |
| `GET /engine/v1/public/agents.json` | Served copy of the manifest | the manifest |
| `GET /engine/v1/public/for-agents` | Served copy of `FOR_AGENTS.md` as text/markdown | raw markdown |

**Auth:** every public endpoint has `dependencies=[]` (no auth) and is explicitly added to the anonymous allowlist in the defensive_perimeter rate limiter. Anonymous tier rate limit applies (10 req/min per IP).

**Response conventions:**
- Every successful response includes `served_by: "agent-memory-unified"` (or whatever the registered agent handle is)
- Every successful response includes `docs: "https://<host>/FOR_AGENTS.md"` — so agents can discover more from any response
- Error responses include `contact: "abuse@<domain>"` so agents know where to report
- Every response includes `schema_version: "1.0"` for forward compatibility
- 429 responses (from the rate limiter) include a `retry_after_seconds` field per FastAPI/slowapi convention

**Internal data scoping:** `trading/api/routes/public.py` imports from internal services but **only calls read-only query methods**. A linter rule (see §8) verifies no mutation methods are called from this file.

### C. Landing route (`trading/api/landing.py`)

The trading API currently responds to `GET /` with a 404. Landing page replaces that with:

```python
@app.get("/")
async def landing():
    return {
        "schema_version": "1.0",
        "name": "agent-memory-unified",
        "description": "Bittensor Subnet 8 validator + multi-agent trading engine",
        "docs": {
            "for_agents": "/FOR_AGENTS.md",
            "agents_manifest": "/.well-known/agents.json",
            "openapi": "/openapi.json",
            "swagger_ui": "/docs",
            "project_feed": "https://github.com/<org>/<repo>/tree/main/project-feed",
            "audit": "https://github.com/<org>/<repo>/blob/main/docs/superpowers/specs/2026-04-10-agent-readiness-audit.md"
        },
        "auth": {
            "public_endpoints": "no auth required",
            "private_endpoints": "X-API-Key header (contact abuse@<domain> for a verified agent key)"
        },
        "rate_limits": {
            "anonymous": "10 req/min",
            "moltbook-verified": "60 req/min",
            "registered": "300 req/min"
        },
        "contact": {
            "abuse": "abuse@<domain>",
            "moltbook": "@<handle>"
        }
    }
```

**Auth:** no auth. Anonymous tier. The landing page is what a bare `GET /` returns.

### D. `FOR_AGENTS.md` content

A single markdown file at the repo root, ~300-500 words, human and agent-readable. Sections (in order):

1. **What this is** — one paragraph. "A multi-agent trading engine + Bittensor Subnet 8 validator. Runs 13 internal agents, operates a gladiator arena with a bookmaker, ships milestone posts to Moltbook as capability announcements. Humans welcome."
2. **Who can call what** — three tiers (anonymous / Moltbook-verified / registered) with 1-sentence descriptions
3. **Rate limits** — the three tiers again, with explicit req/min numbers
4. **Public endpoints** — bullet list of each endpoint from §B with a one-liner
5. **Authenticated endpoints** — brief mention that `/openapi.json` has the full list, link to it
6. **Abuse reporting** — email address (TBD) + what to include in a report
7. **Terms** — 3 bullets pointing at `TERMS_FOR_AGENTS.md`
8. **Moltbook handle** — `@<handle>` once registered
9. **Source of truth for changes** — link to `project-feed/` directory
10. **Contact for coordination** — "If you want to build something together, post in [submolt] mentioning @<handle>"

### E. `agents.json` schema

```json
{
  "schema_version": "1.0",
  "name": "agent-memory-unified",
  "description": "Bittensor Subnet 8 validator + multi-agent trading engine with a gamified competition arena",
  "operator": {
    "type": "human-owned",
    "contact": "abuse@<domain>",
    "verification": {
      "platform": "moltbook",
      "handle": "@<handle>",
      "profile_url": "https://www.moltbook.com/u/<handle>"
    }
  },
  "capabilities": {
    "read": [
      "arena:state",
      "arena:leaderboard",
      "knowledge-graph:query",
      "knowledge-graph:timeline",
      "milestones:list",
      "agents:list",
      "status"
    ],
    "write": [],
    "experimental": []
  },
  "auth": {
    "methods": ["anonymous", "moltbook-identity", "api-key"],
    "anonymous_endpoints": ["/engine/v1/public/*", "/", "/.well-known/agents.json", "/openapi.json", "/docs", "/redoc"],
    "api_key_header": "X-API-Key",
    "moltbook_identity_header": "X-Agent-Token"
  },
  "rate_limits": {
    "anonymous": { "requests_per_minute": 10, "scope": "read-only allowlist" },
    "moltbook-verified": { "requests_per_minute": 60, "scope": "read + low-risk writes" },
    "registered": { "requests_per_minute": 300, "scope": "scope-gated full surface" }
  },
  "endpoints": [
    {
      "path": "/engine/v1/public/status",
      "method": "GET",
      "auth_required": false,
      "description": "Project liveness + version + uptime"
    },
    {
      "path": "/engine/v1/public/agents",
      "method": "GET",
      "auth_required": false,
      "description": "List of internal agents with strategies"
    },
    {
      "path": "/engine/v1/public/arena/state",
      "method": "GET",
      "auth_required": false,
      "description": "Current arena match, season, top leaderboard"
    },
    {
      "path": "/engine/v1/public/leaderboard",
      "method": "GET",
      "auth_required": false,
      "description": "Full public leaderboard with Elo + outcomes"
    },
    {
      "path": "/engine/v1/public/kg/entity/{name}",
      "method": "GET",
      "auth_required": false,
      "description": "Temporal knowledge graph facts for a named entity"
    },
    {
      "path": "/engine/v1/public/kg/timeline",
      "method": "GET",
      "auth_required": false,
      "description": "Chronological KG timeline"
    },
    {
      "path": "/engine/v1/public/milestones",
      "method": "GET",
      "auth_required": false,
      "description": "Recent project-feed milestone posts"
    }
  ],
  "milestones_feed": "https://github.com/<org>/<repo>/tree/main/project-feed",
  "openapi": "/openapi.json",
  "for_agents": "/FOR_AGENTS.md",
  "terms": "/TERMS_FOR_AGENTS.md",
  "abuse_reporting": {
    "email": "abuse@<domain>",
    "endpoint": null,
    "response_sla_hours": 24
  },
  "incident_history": [],
  "last_updated": "2026-04-10T00:00:00Z"
}
```

Placeholders (`<domain>`, `<handle>`, `<org>`, `<repo>`) are literal until the operator populates them.

### F. Internal data scoping — what NOT to expose

Hard rules enforced by code review + the linter mentioned in §8:

- **No wallet addresses, private keys, or Bittensor coldkey/hotkey data** in any response
- **No internal API keys, `STA_*` env values, or secrets** in any response
- **No user email addresses or PII**
- **No raw SQL query strings or error stack traces** in responses — errors return `{error: "<sanitized>", contact: "abuse@<domain>"}` only
- **No internal agent IDs that could be used to call privileged endpoints** — only the human-readable agent names from `agents.yaml`
- **No trading positions, order history, or broker account info** — the public surface covers arena/gamification data, not live trading P&L
- **No memory contents** — the L0/L1 context layers live behind auth, not on the public surface. KG is an intentional exception (it's designed to be queryable), but only the public `kg.*` endpoints, not raw memory rows

## 4. Tech Stack

- **Backend:** Python 3.13, FastAPI
- **Static files:** Vite (`frontend/public/.well-known/`) + FastAPI fallback route
- **Rate limiting:** `slowapi` (consumed from `defensive_perimeter` track)
- **Markdown serving:** FastAPI `Response(media_type="text/markdown")` reading from `trading/public_content/FOR_AGENTS.md`
- **Linter:** custom pytest test (`trading/tests/unit/test_public_surface_scoping.py`) that AST-parses `routes/public.py` and verifies no mutation methods are called

## 5. Dependencies

- **Hard dependency:** `defensive_perimeter` track must have the anonymous rate limit tier wired before public routes can be safely exposed. If public routes ship before rate limiting, an external agent can hit `/engine/v1/public/kg/timeline` at line rate and fill the database's query buffer.
- **Soft dependency:** `agent_identity` track (Phase B) — public endpoints don't need real identity, but `FOR_AGENTS.md` describes the three tiers honestly, which requires knowing when Phase B will land to describe "moltbook-verified" accurately.
- **Coordination with `moltbook_publisher` track:** the `GET /engine/v1/public/milestones` endpoint reads from `project-feed/*.md` with `status: posted`, which only starts appearing once the publisher runs at least once. Until then, the endpoint returns an empty list with a `note: "No milestones published yet"` message.

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Public KG endpoints expose sensitive internal reasoning | `kg.entity` + `kg.timeline` return only public-tagged triples (tag filter at query time) — a new `kg.public` boolean column added in a small follow-up migration OR a hardcoded entity allowlist at v1 |
| Landing route leaks internal URLs or infra details | Response body is a static dict with explicit fields — no dynamic reflection of internal state |
| `agents.json` becomes stale as endpoints are added/removed | A pytest test compares the `endpoints` array in `agents.json` to the actual routes in `routes/public.py` and fails on drift |
| Rate limit misconfiguration lets external agents saturate the trading engine | `defensive_perimeter` Phase A is a hard dependency; this track will not ship before it lands |
| `FOR_AGENTS.md` becomes stale as capabilities change | Linked from every response (`docs` field); operator reviews monthly OR whenever a new public endpoint lands (enforced by checklist in the pytest test above) |
| Frontend Vite + FastAPI both serving `.well-known/agents.json` produces drift | Canonical source is `trading/public_content/agents.json`; frontend copies via a postbuild script or a symlink checked in git |
| Sensitive endpoints accidentally end up in `/engine/v1/public/` | The linter mentioned in §8 AST-parses `routes/public.py` and rejects any import of mutation-capable services |

## 7. Quality gates (must pass before merge)

- [ ] **Public surface linter passes:** `trading/tests/unit/test_public_surface_scoping.py` verifies `routes/public.py` imports no mutation-capable services and all handlers have `dependencies=[]` or the explicit anonymous dependency.
- [ ] **`agents.json` schema validates:** A JSON schema (`trading/tests/schemas/agents.schema.json`) covers the manifest shape; test validates the served file against it.
- [ ] **Endpoints match manifest:** Pytest diff between the `endpoints` array in `agents.json` and the routes collected from `routes/public.py` — fails on drift.
- [ ] **Rate limit integration test:** 11 rapid requests to `/engine/v1/public/status` from the same IP return 10 × 200 and 1 × 429 with a `retry_after_seconds` field.
- [ ] **Landing route smoke test:** `GET /` returns a 200 with `schema_version`, `name`, `docs`, `rate_limits`, `contact` fields present.
- [ ] **FOR_AGENTS.md served:** `GET /engine/v1/public/for-agents` returns the file content with `text/markdown` content type.
- [ ] **No-secrets test:** grep for `STA_`, `B64_`, `api_key`, `secret`, `token`, `password`, `wallet`, `hotkey`, `coldkey` in any public response body — must return zero matches.
- [ ] **Public KG endpoint respects the public filter:** a test adds a non-public KG triple and confirms it does NOT appear in `/engine/v1/public/kg/entity/{name}` responses.

## 8. Out of scope / future work

- **Write endpoints for external agents** (Phase D proper) — arena participation, bookie betting, signal submission. Requires `agent_identity` track.
- **Moltbook identity federation** — accepting Moltbook `X-Moltbook-Identity` headers and treating them as an authenticated tier. Requires `agent_identity` + specific Moltbook integration work.
- **Rich incident reporting flow** — a `POST /engine/v1/public/abuse/report` endpoint. Defer to `abuse_response` track (work stream ζ).
- **Multi-language `FOR_AGENTS.md`** — i18n is a stretch goal.
- **Graph visualizations for KG queries** — pure data API for v1; viz can come later.
- **SSE or WebSocket streaming public endpoints** — no streaming in v1; pure REST.
- **Pagination for `/leaderboard` and `/milestones`** — fixed limits (top 50) in v1; pagination is a follow-up if we actually see high traffic.

## 9. References

- Audit: `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- Companion: `conductor/tracks/public_surface/audit-cross-ref.md`
- Sibling tracks: `conductor/tracks/defensive_perimeter/` (hard dependency), `conductor/tracks/moltbook_publisher/` (shares milestones endpoint)
- Moltbook context: `reference_moltbook.md`
- Project-feed convention: `reference_project_feed_convention.md`
