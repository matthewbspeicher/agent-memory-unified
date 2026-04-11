# Cross-reference: Agent-Readiness Audit ↔ Moltbook Publisher

**Created:** 2026-04-10
**By:** Claude Code
**Purpose:** Map this track's scope to the agent-readiness audit findings. Same pattern as the `defensive_perimeter`, `public_surface`, and `intelligence_memory` cross-refs.

## Track identity

This is **work stream ε** from the Moltbook integration plan in `reference_moltbook.md`. Unlike `defensive_perimeter` and `public_surface`, this track is not strictly about closing audit findings — it's about shipping the **publishing infrastructure** that, combined with the other tracks, lets the Moltbook integration actually happen. But it still has audit-relevant implications that are worth documenting explicitly.

## Audit findings this track relates to (indirectly)

This track doesn't *close* any audit findings — it's about the outbound direction (we post to Moltbook), not the inbound direction (external agents hit our API). The audit is almost entirely about protecting *our* API from *their* traffic. This track is about being a well-behaved *caller* of *their* API.

That said, two findings are indirectly relevant:

| Audit dimension | Risk | Relevance |
|---|---|---|
| 🔴 #5 Write surface protection | Critical | **Indirect.** The publisher writes to files in `project-feed/` (frontmatter updates after successful posts). Those writes are local filesystem operations, not HTTP endpoints, so they're outside the audit's HTTP threat model. But the frontmatter-round-trip logic is a **write** operation on source-of-truth content, so it gets the same care: body bytes preserved exactly, idempotent, refuses to re-post files already marked `posted`. |
| 🟠 #6 Audit logs on writes | High | **Indirect.** The publisher's own output (successful post UUID, rate limit state updates) is persisted to `scripts/.moltbook-state.json` — effectively a local audit log of the publisher's actions. Not wired to the Postgres `audit_logs` table from `defensive_perimeter` because it's run out-of-band from the trading API, but the same principle applies. |

## Audit findings this track does NOT address

This is the majority. Most of the audit is about inbound traffic; this track is about outbound traffic to one specific platform. Explicitly out of scope:

| Audit dimension | Risk | Why out of scope |
|---|---|---|
| 🔴 #2 Rate limiting (our API) | Critical | We're the *caller* here, not the callee. The publisher respects **Moltbook's** rate limits, not ours. Our rate limiting lives in `defensive_perimeter`. |
| 🔴 #5 Write surface (our API) | Critical | Publisher writes to Moltbook's API, not ours. Our write surface is `defensive_perimeter`'s problem. |
| 🔴 #8 Per-agent resource limits | Critical | The publisher doesn't run agents; it posts content on behalf of one Moltbook identity. LLM budgets are `intelligence_memory`'s concern. |
| 🟠 #1 Identity & auth | High | The publisher uses ONE Moltbook API key for ONE Moltbook identity. Multi-agent identity for our own API is `agent_identity`'s concern. |
| 🟡 #3 Agent-readable docs | Medium | `FOR_AGENTS.md` and `agents.json` are `public_surface`'s concern. |
| 🟢 #4 Content to consume | Low | `project-feed/` already exists. |
| 🟡 #7, #9, #10 | Medium | Concurrency / observability / coordination — not publisher concerns. |

## Dependencies

### Hard dependencies

- **`project-feed/` directory** with at least one `status: ready` entry. The directory already exists (committed as `a66adb9`) with one draft post and four stubs; the publisher is fully functional against the current state, though nothing is `status: ready` yet.
- **`MOLTBOOK_API_KEY`** environment variable. This is blocked on the **one human-only step** in the entire Moltbook integration: the operator (mspeicher) has to register the agent on moltbook.com and complete the Twitter verification. The `register-wizard` subcommand exists specifically to walk through that process, but it cannot automate the Twitter step.

### Soft dependencies (nice but not required)

- **None.** The publisher is deliberately standalone. It doesn't touch the trading API, the KG, the agent runtime, the Bittensor integration, or the frontend. It can be built, tested, and committed without any other track landing first. **This is intentional** — it means the publisher can be development-ready and waiting the moment the operator completes the registration step.

## Unblocks

- **First Moltbook post** — this track is the literal mechanism for publishing. Combined with `defensive_perimeter` (protecting the callee surface), `public_surface` (installing the door), and `agent_identity` (real per-agent identity), plus the human registration step, this track is the thing that actually puts a post on Moltbook.
- **`public_surface`'s `/engine/v1/public/milestones` endpoint** — that endpoint reads files with `status: posted` from `project-feed/`. Until the publisher runs at least once, the endpoint returns an empty list. First publisher run → first `status: posted` → first non-empty milestones endpoint response.

## Shares primitives with

- **`public_surface`** — both tracks touch `project-feed/`. The publisher writes (frontmatter updates). `public_surface` reads (via the `/milestones` endpoint). They're designed to work together without interfering.
- **`project_feed` convention** — the publisher is the **reference implementation** of the frontmatter conventions documented in `reference_project_feed_convention.md`. The convention was written first (when `project-feed/` was seeded); the publisher validates and enforces it.

## Security considerations (per spec §6)

The publisher is the **only place in the repo that holds the `MOLTBOOK_API_KEY`**. Defense in depth:

1. **`.env` gitignored** — the API key never leaves the local machine
2. **`.moltbook-state.json` gitignored** — contains post UUIDs + timestamps, not the key, but kept out of git for repo cleanliness
3. **HTTPS only** — `BASE_URL` hardcoded to `https://www.moltbook.com`
4. **Secret scanner** — every post body is scanned for 10+ forbidden patterns before network send
5. **Dry-run default** — actual posting requires explicit `--yes` + no `--dry-run`
6. **Moltbook breach awareness** — `reference_moltbook.md` documents two 2026 breaches; the publisher assumes the API key may be rotated and surfaces "re-register if needed" in all failure messages

## Hard gate restated

Per the audit's recommended sequence: **do not run `publish` against the real Moltbook API until**:

1. `defensive_perimeter` (Phase A) landed — rate limiting, audit decorator, kill-switch protection ✗
2. `agent_identity` (Phase B) landed or explicit acceptance of attribution-only identity ✗
3. `public_surface` track landed — `FOR_AGENTS.md`, `/.well-known/agents.json`, read-only public endpoints ✗
4. This track (`moltbook_publisher`) landed — the publisher itself ✗
5. 2-3 polished posts in `project-feed/` with `status: ready` ✗ (one draft + four stubs currently)
6. Human registration step: Moltbook account + Twitter verification ✗ (can only be done by the operator)

Tasks 1-7 of this plan can all be **implemented and committed** before any of these gates open. The publisher can be fully built, tested against a mocked Moltbook API, and ready to run — sitting idle until the operator says "go" and the six gates align.

**The publisher never publishes until it's told to.** That's the design principle. Every safety net — dry-run default, secret scan, rate limit check, interactive confirmation, explicit `--yes` — exists to make "accidentally published something bad" impossible without the operator explicitly accepting risk.

## Pointers

- Audit (full): `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- This track's spec: `conductor/tracks/moltbook_publisher/spec.md`
- This track's plan: `conductor/tracks/moltbook_publisher/plan.md`
- Sibling tracks: `defensive_perimeter`, `public_surface`, `intelligence_memory`
- Moltbook reference: `reference_moltbook.md` (API shape, rate limits, security history, skill.md onboarding)
- Project-feed convention: `reference_project_feed_convention.md` (frontmatter schema, status lifecycle, drafts/ handling)
- Moltbook API skill file: `https://www.moltbook.com/skill.md`
- Moltbook API GitHub repo: `https://github.com/moltbook/api`
