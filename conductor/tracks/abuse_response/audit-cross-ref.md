# Cross-reference: Agent-Readiness Audit ↔ Abuse Response

**Created:** 2026-04-10
**By:** Claude Code
**Purpose:** Map this track's scope to the agent-readiness audit. Same pattern as the other cross-ref docs.

## Track identity

This is the **sixth and last track** in the current audit-driven roadmap. It ships the operational complement to the technical defenses from `defensive_perimeter` and `agent_identity`: the "what happens when things go wrong" layer. Audit Phase E work, plus the operational foundations that don't fit neatly into any of the other five tracks.

## Audit findings this track targets

| Audit dimension | Risk | Coverage |
|---|---|---|
| 🟡 #9 Observability | Medium | **Partial close** — ships a Grafana dashboard JSON with 10 panels keyed on `agent_id` (populated by defensive_perimeter's `@audit_event` + agent_identity's `resolve_identity`). Actual Grafana instance provisioning is out of scope (assumed to exist or be provisioned separately). |
| (no direct finding) | n/a | **Fills an operational gap** — the audit recommended Phase A/B/C/D tracks to close specific technical findings, but it also noted that "knowing what to do when the system gets hit" is a separate question. This track is that answer: incident response runbook, kill-switch operations playbook, abuse contact, Sentry alert rules, post-incident review template, abuse report endpoint. None of these are individually audit-critical — collectively, they're the difference between "we have defenses" and "we can operate under attack." |

The audit did NOT list abuse-reporting as a finding because it framed the threat model as "protect the API," not "receive feedback from visitors." This track is additive to the audit — a belt-and-suspenders layer.

## Audit findings this track does NOT address (intentionally)

| Audit dimension | Risk | Why |
|---|---|---|
| 🔴 #2, #5, #8 | Critical | Technical defenses — belong to `defensive_perimeter` and `agent_identity`. |
| 🟠 #1, #6 | High | Identity + audit logs — `agent_identity` and `defensive_perimeter`. |
| 🟡 #3, #4, #7, #10 | Low-Medium | Docs/content/concurrency/coordination — `public_surface` / adequate / internal. |

This track is **pure operational layer**. It assumes the technical defenses exist and works on top of them.

## Dependencies

### Hard dependencies

- **`defensive_perimeter` Phase A landed** — the `@audit_event` decorator populates `audit_logs` which the Grafana dashboard queries. The kill-switch two-step flow exists for the runbook to reference. The rate limiter's anonymous tier protects the abuse report endpoint.
- **`public_surface` track landed** — the abuse report endpoint lives at `POST /engine/v1/public/abuse/report`, under the public router prefix. Inherits the anonymous rate limit tier automatically.

### Soft dependencies

- **`agent_identity` track landed** — the incident response runbook's "how to ban a misbehaving agent" section assumes `POST /api/v1/identity/agents/{name}/revoke` exists. Without it, the runbook gracefully degrades to "rotate the master API key" as the coarsest ban mechanism.
- **`intelligence_memory`'s structured logging framework** — the Sentry alert rules key on event types (`risk.kill_switch.activated`, `memory.write`, etc.) emitted via `log_event()`. Without structured logging, the alert rules can't pattern-match cleanly and fall back to generic error-count thresholds.
- **`moltbook_publisher` track** — the runbook has a section on "rotating the Moltbook API key if it leaks"; that section is only meaningful if the publisher exists. Marked as TODO if `moltbook_publisher` hasn't landed yet.

### External dependencies (not tracks)

- **Grafana instance** — provisioned separately. The dashboard JSON is shipped, but the instance itself is not in scope.
- **Sentry project configured** — `SENTRY_DSN` already wired in `trading/api/app.py:2043-2057`. The alert rules doc walks the operator through configuring them in the Sentry UI; not automated.

## Unblocks

- **Safe invitation of external agent traffic** — this track is part of Phase D's "operational readiness" gate. Rate limiting + real identity + audit logs give you technical protection; runbooks + dashboards + alerts give you the ability to *respond* when protection is insufficient. Both are needed before the first Moltbook post.
- **Post-incident learning** — the template makes retrospectives cheap. Low friction = more incidents reviewed = faster learning loop.

## Shares primitives with

- **`defensive_perimeter`** — consumes the `audit_logs` table, the `@audit_event` decorator, the kill-switch two-step flow, the `slowapi` rate limiter.
- **`agent_identity`** — consumes `resolve_identity` for the abuse report endpoint (so reporter is attributed to the authenticated agent name if present). Runbook references `require_scope("admin")` for operator actions.
- **`public_surface`** — the abuse report endpoint lives under `/engine/v1/public/abuse/report` and is linked from `FOR_AGENTS.md` and `/.well-known/agents.json`.
- **`moltbook_publisher`** — the runbook references the publisher for "rotating Moltbook API key" scenarios; the Grafana dashboard has a panel for publisher status (optional, v2).

## Design decisions worth knowing

1. **Reporter IP stored as `sha256(ip + salt)`**, not plaintext. Satisfies the "no PII in logs" audit concern while keeping correlation ability for repeated reports from the same source. Salt is config-driven (`STA_IP_HASH_SALT` env var).
2. **Runbooks are markdown, not YAML or structured data.** Humans read them during incidents; reaching for a parser during a 3am outage is the wrong UX. Automated validation is limited to "file exists and has a title heading."
3. **Kill-switch runbook has an integration test.** Every curl command in the runbook is exercised by `trading/tests/integration/test_kill_switch_runbook.py` so code/doc drift is caught in CI.
4. **Grafana dashboard is shipped as JSON, not provisioned.** The dashboard JSON is versioned in git; the operator imports it once via the Grafana UI. Provisioning is a separate infrastructure concern.
5. **Sentry alert rules are documented, not automated.** Same reasoning — the operator configures them once via the Sentry UI following `docs/runbooks/sentry-alerts.md`.
6. **Abuse report categories are fixed.** `bug | rate-limit | content | identity | security | other`. Pydantic `Literal` type enforces this. Adding categories requires a spec update.
7. **No automated triage workflow.** V1 triages via direct SQL queries. Triage UI is v2.
8. **Single-operator assumption.** No on-call rotation, no handoff protocol. Documented limitation.

## Hard gate position

This track is the **"operational readiness" piece** of the Moltbook publication gate. Not technically blocking the first post — you *could* publish without runbooks and rely on ad-hoc response — but shipping without this track means:
- No written abuse contact → first abuse report goes to /dev/null
- No runbook → first incident is improvised at 3am
- No Grafana dashboard → first traffic spike is invisible
- No Sentry alerts → first bug in production surfaces via Moltbook comments, not pages

Recommendation: treat this track as a **strong soft gate** for the first Moltbook post. It can be partial (runbooks + dashboard exist; alert rules configured) without all tasks complete, but the absence of any operational layer at all is a significant risk for the first public interaction.

## Pointers

- Audit (full): `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- This track's spec: `conductor/tracks/abuse_response/spec.md`
- This track's plan: `conductor/tracks/abuse_response/plan.md`
- Sibling cross-refs: `defensive_perimeter`, `agent_identity`, `public_surface`, `moltbook_publisher`, `intelligence_memory`
- Memory: `reference_agent_readiness_audit.md`, `reference_moltbook.md` (breach history is especially relevant to the abuse response posture), `feedback_parallel_opencode_stream.md`
