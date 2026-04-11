# Specification: Abuse Response & Operational Readiness

## 1. Objective

Ship the "what happens when things go wrong" layer. This track is the operational complement to `defensive_perimeter` (which ships the technical defenses) and `agent_identity` (which ships real auth). It lands the pieces that turn "a system that's hard to attack" into "a system you can actually operate under attack": abuse reporting channel, incident response runbook, per-agent observability dashboards, alerting rules, kill-switch operations playbook, and a simple post-incident review template.

This is **audit Phase E** work plus the operational foundations needed before inviting external agent traffic via Moltbook.

## 2. Non-goals

- **Full SOC / 24x7 response capability.** This is a single-operator project; the playbook assumes one person + reasonable response times (hours, not minutes).
- **Automated remediation.** No auto-ban, no auto-quarantine, no ML-based anomaly detection. Humans in the loop for every consequential action.
- **Threat intelligence feeds.** No blocklist subscriptions, no IP reputation databases, no WAF rules. Scope is "respond to what we observe," not "predict what's coming."
- **PCI / SOC 2 / compliance documentation.** This is operational readiness, not regulatory compliance. Different track entirely.
- **Public-facing status page.** `GET /engine/v1/public/status` already exists from `public_surface`; that's enough for v1.
- **Incident escalation to external parties.** No on-call rotation, no PagerDuty integration, no Opsgenie. Single operator, single email.

## 3. Architecture & Design

### A. Abuse contact + report endpoint

**Static contact** published in four places, all pointing at the same email alias:
- `FOR_AGENTS.md` at repo root (from `public_surface` track)
- `/.well-known/agents.json` `abuse_reporting.email` field (from `public_surface`)
- `GET /` landing route `contact.abuse` field (from `public_surface`)
- `docs/runbooks/abuse-contact.md` (owned by this track)

**Dynamic endpoint:** `POST /engine/v1/public/abuse/report` — anyone can submit a report, anonymous or authenticated. The endpoint:

```python
# trading/api/routes/abuse.py
from api.identity.dependencies import resolve_identity, Identity
from fastapi import APIRouter, Depends
from typing import Annotated

router = APIRouter(prefix="/engine/v1/public/abuse", tags=["abuse"])

class AbuseReport(BaseModel):
    category: str = Field(..., description="bug | rate-limit | content | identity | other")
    description: str = Field(..., min_length=10, max_length=5000)
    affected_resource: str | None = None
    evidence: str | None = None  # URL, request ID, timestamp, etc.
    reporter_contact: str | None = None  # email or Moltbook handle for follow-up

@router.post("/report")
async def submit_abuse_report(
    report: AbuseReport,
    identity: Annotated[Identity, Depends(resolve_identity)],
):
    """Submit an abuse report. Anonymous allowed. Rate-limited."""
    report_id = await AbuseStore.insert(
        category=report.category,
        description=report.description,
        affected_resource=report.affected_resource,
        evidence=report.evidence,
        reporter_name=identity.name,
        reporter_contact=report.reporter_contact,
        submitted_at=datetime.utcnow(),
    )
    # Emit Sentry alert for high-severity categories
    if report.category in ("identity", "security"):
        capture_message(f"High-severity abuse report {report_id}", level="warning")
    return {
        "report_id": report_id,
        "received_at": datetime.utcnow().isoformat(),
        "status": "submitted",
        "follow_up": "abuse@<domain> will review within 24 hours",
        "served_by": "agent-memory-unified",
    }
```

**Auth:** `resolve_identity` (anonymous allowed). Rate-limited via the anonymous tier from `defensive_perimeter` (10 req/min per IP). Optionally add a tighter per-endpoint limit (1 per minute) to prevent report flooding.

**Storage:** A new Postgres table `abuse_reports` in the existing `defensive_perimeter` `audit_logs` schema (or its own schema — see §3.G migration strategy).

### B. Incident response runbook (`docs/runbooks/incident-response.md`)

One-page, decision-tree-structured runbook. Sections:

1. **"I think something is wrong" — where to look first**
   - Check `GET /engine/v1/public/status` — is the API up?
   - Check `GET /api/v1/risk/kill-switch/status` (master-key) — is the system halted?
   - Check `tail -f` on structured logs — are there 5xx bursts? rate-limit 429 spikes?
   - Check Sentry dashboard — new error types in the last hour?
   - Check Grafana per-agent dashboard — any agent with a sudden request spike?

2. **"How to halt everything immediately"**
   - Two-step kill-switch from `defensive_perimeter`: `/initiate` → `/confirm`
   - Follow-up: set `STA_RATE_LIMIT_ENABLED=false` and restart (nuclear, only if rate limiter itself is the problem)

3. **"How to ban a misbehaving agent"** (assumes `agent_identity` track landed)
   - Get the agent name from logs (`audit_logs.actor_id` column or `queried_by` in public endpoint responses)
   - `POST /api/v1/identity/agents/{name}/revoke` with `reason: "<incident summary>"`
   - Verify with `GET /api/v1/identity/agents/{name}` (should 404)
   - Log the revocation in the incident review doc

4. **"How to rotate the master API key if it leaks"**
   - Generate a new key (128 bits, e.g., `openssl rand -hex 32`)
   - Update `STA_API_KEY` in the server's `.env`
   - Restart the trading engine
   - Update Railway env vars via `railway vars set`
   - Notify anyone holding the old key (if applicable)

5. **"How to rotate the Moltbook API key"**
   - Register a new agent on Moltbook OR use Moltbook's rotation flow (if it exists — verify in spec)
   - Update `MOLTBOOK_API_KEY` in `trading/.env`
   - Re-run `python scripts/publish-to-moltbook.py status` to confirm

6. **"How to tell if we've been breached"** — signals to look for:
   - Audit log entries with `status: success` from unexpected `actor_id`
   - New `identity.agents` rows not created by the operator
   - `identity.audit_log` events the operator doesn't recognize
   - Changes to `scripts/init-trading-tables.sql` or migrations not made by the operator
   - New outbound connections from the trading engine to unfamiliar hosts

7. **"How to preserve evidence during an incident"**
   - Dump the `audit_logs` table: `pg_dump -t audit_logs > audit_$(date +%s).sql`
   - Save the last hour of logs: `docker logs agent-memory-unified-trading-1 --since 1h > logs_$(date +%s).log`
   - Screenshot the Grafana dashboard
   - Create a post-incident review entry (template in `docs/runbooks/post-incident-review-template.md`)

8. **"When to fully restart from a clean state"** — criteria and procedure
9. **"When to reach out to Moltbook / file an issue"** — criteria (breach disclosure, malicious agents using our platform, etc.)

### C. Grafana dashboard — per-agent observability

A new Grafana dashboard config at `docs/grafana/agent-observability.json` with panels keyed on `agent_id` from the `audit_logs` table populated by `defensive_perimeter`'s `@audit_event` decorator + `agent_identity`'s `resolve_identity`.

**Panels:**

1. **Request rate per agent** — stacked time series, `rate(audit_logs count) by (actor_id)` over 5m windows
2. **Error rate per agent** — time series, `rate(audit_logs where status='failed') by (actor_id)`
3. **Rate-limit 429 count per IP** — top 10 IPs by 429 count in the last hour
4. **Slow endpoints per route** — p95/p99 `duration_ms` by `http_path` top 20
5. **Kill-switch status** — single-value panel, reads `kill_switch:active` Redis key
6. **New identities in the last 24h** — count from `identity.audit_log` with `event='created'`
7. **Revocations in the last 24h** — count from `identity.audit_log` with `event='revoked'`
8. **Public endpoint hit count** — bar chart, top 10 public endpoints by request count
9. **Abuse reports in the last 24h** — count + category breakdown from `abuse_reports` table
10. **Moltbook publisher status** — scrape the `.moltbook-state.json` file or expose a `/api/v1/moltbook/publisher/status` admin endpoint (optional v2)

**Deployment:** the Grafana instance is assumed to already exist (or to be added separately). This track ships the **dashboard JSON config**, not the Grafana instance itself. Import via Grafana's "Import dashboard JSON" UI, or provision via Grafana's API.

**Out of scope for this track:** standing up a Grafana instance if one doesn't exist. That's infrastructure setup, not a defensive-perimeter concern.

### D. Sentry alerting rules

Sentry is already wired in `trading/api/app.py:2043-2057` (if `SENTRY_DSN` is set). This track adds **alert rules** — configured in the Sentry UI or via the Sentry API.

Rules to configure:

| Rule | Condition | Severity | Action |
|---|---|---|---|
| Kill-switch activated | Log event `risk.kill_switch.activated` | Critical | Email + Slack (if wired) |
| Sustained 5xx spike | `issue.count > 10` in 5m on any endpoint | Warning | Email |
| Rate-limit 429 flood from one IP | `custom.429_per_ip > 100` in 5m | Warning | Email |
| Identity creation anomaly | `identity.audit_log.event='created'` count > 5 in 1h | Warning | Email (might indicate operator automating something or an incident) |
| Audit log write failure | Any exception in `@audit_event` decorator sink | Critical | Email |
| Moltbook publisher failure | Any exception in `publish-to-moltbook.py` run | Info | Log only (not critical; operator sees it) |
| Database connection errors | `asyncpg` errors > 5 in 5m | Critical | Email |
| Broker rate-limit errors | `BrokerError.RateLimitExceeded` > 10 in 1h | Warning | Email |

**Delivery:** rules are documented in `docs/runbooks/sentry-alerts.md` with exact configuration steps (Sentry UI path + the exact condition/threshold/action). This track does NOT automatically provision the rules — the operator runs through the doc once to set them up.

### E. Kill-switch operations playbook

A standalone runbook at `docs/runbooks/kill-switch-operations.md` covering:

1. **Who has access** — the master `STA_API_KEY` holder (operator) and anyone with an `admin`-scoped agent token (usually nobody, per `agent_identity` spec)
2. **How to trigger** — the two-step `/initiate` → `/confirm` flow from `defensive_perimeter`:
   ```bash
   # Step 1: get confirmation token (60s expiry)
   TOKEN=$(curl -sX POST http://localhost:8080/api/v1/risk/kill-switch/initiate \
     -H "X-API-Key: $STA_API_KEY" | jq -r .confirmation_token)

   # Step 2: confirm within 60s
   curl -X POST http://localhost:8080/api/v1/risk/kill-switch/confirm \
     -H "X-API-Key: $STA_API_KEY" \
     -d "{\"token\": \"$TOKEN\"}"
   ```
3. **What it blocks** — all `POST/PUT/DELETE` across the trading API (per `defensive_perimeter` spec). GET requests continue to work.
4. **What it does NOT block** — internal agent scans at the next check-point boundary (up to ~30s lag), already-in-flight broker orders (the broker confirms them separately), SSE streams.
5. **How to verify it's active** — `curl http://localhost:8080/api/v1/risk/kill-switch/status` (master key). Also visible in the Grafana dashboard panel #5.
6. **How to deactivate** — `POST /api/v1/risk/kill-switch/deactivate` with two-step confirmation (same pattern as activation). Log the reason.
7. **When NOT to trigger** — if the problem is isolated to one endpoint or one agent, revoke the agent (see §B.3) or disable the specific route instead. Kill-switch is the nuclear option.
8. **Post-kill-switch recovery** — restart order: verify the underlying incident is resolved → deactivate kill-switch → monitor the Grafana dashboard for 30 minutes → resume normal operations.

### F. Post-incident review template

`docs/runbooks/post-incident-review-template.md` — a ~1-page markdown template to copy-paste after any incident. Sections:

```markdown
# Post-Incident Review: <brief title>

**Date:** YYYY-MM-DD
**Severity:** Critical / High / Medium / Low
**Duration:** <start> → <end>
**Author:** <operator name>
**Status:** Draft / Under review / Published

## Summary

One-paragraph description of what happened, visible impact, and how it was resolved.

## Timeline (UTC)

| Time | Event |
|---|---|
| HH:MM | <first signal — log entry, alert, report> |
| HH:MM | <triage decision> |
| HH:MM | <kill-switch activated / agent revoked / etc.> |
| HH:MM | <root cause identified> |
| HH:MM | <fix applied> |
| HH:MM | <kill-switch deactivated / recovery> |
| HH:MM | <confirmed stable> |

## What went wrong

Root cause, in plain language. Include code references if relevant.

## What went right

What worked as intended? What made the response faster?

## What went badly

What slowed the response? What wasn't in the runbook that should have been?

## Action items

- [ ] <concrete fix to prevent recurrence>
- [ ] <runbook update>
- [ ] <test to catch this in the future>
- [ ] <follow-up PR>

## Evidence preserved

- [ ] audit_logs dump: `audit_<ts>.sql`
- [ ] Application logs: `logs_<ts>.log`
- [ ] Grafana screenshots: `<path>`
- [ ] Sentry issue link: `<url>`

## Moltbook status

- [ ] Post updated with "incident" status if applicable
- [ ] Follow-up post published describing root cause (if appropriate)
- [ ] Abuse contact notified of any external parties affected
```

### G. `abuse_reports` table migration

```sql
-- scripts/migrations/add-abuse-reports.sql
CREATE SCHEMA IF NOT EXISTS incident;

CREATE TABLE IF NOT EXISTS incident.abuse_reports (
    id                 BIGSERIAL PRIMARY KEY,
    submitted_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category           TEXT NOT NULL,     -- 'bug' | 'rate-limit' | 'content' | 'identity' | 'security' | 'other'
    description        TEXT NOT NULL,
    affected_resource  TEXT,
    evidence           TEXT,
    reporter_name      TEXT,              -- from resolve_identity — 'anonymous', 'master', or an agent name
    reporter_contact   TEXT,              -- optional self-provided email / handle
    reporter_ip_hash   TEXT,              -- sha256(client_ip + salt), not the raw IP
    status             TEXT NOT NULL DEFAULT 'new',  -- 'new' | 'triaged' | 'in-progress' | 'resolved' | 'dismissed'
    triaged_at         TIMESTAMPTZ,
    triaged_by         TEXT,
    resolution         TEXT
);

CREATE INDEX IF NOT EXISTS idx_abuse_reports_submitted_at ON incident.abuse_reports(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_abuse_reports_category ON incident.abuse_reports(category, status);
CREATE INDEX IF NOT EXISTS idx_abuse_reports_status ON incident.abuse_reports(status) WHERE status != 'resolved';
```

**Same migration mechanism** as `identity` schema and `defensive_perimeter`'s `audit_logs` — a file in `scripts/migrations/` applied via `psql` on deploy.

**IP privacy:** reporter IP is stored as `sha256(ip + salt)`, not plaintext. Satisfies the "no PII in logs" spirit from the audit while keeping the ability to correlate reports from the same source.

## 4. Tech Stack

- **Language:** Python 3.13 (matches existing trading engine)
- **Database:** Postgres 16 (same instance, new `incident` schema)
- **Observability:** Grafana (existing or provisioned separately), Sentry (already wired)
- **Documentation format:** Markdown runbooks under `docs/runbooks/`
- **Testing:** `pytest` for the abuse report endpoint + schema; manual walkthroughs for the runbooks (not automatable)

No new Python dependencies. All stdlib + existing project deps.

## 5. Dependencies

### Hard dependencies

- **`defensive_perimeter` Phase A landed** — the `@audit_event` decorator, the `audit_logs` Postgres table, the kill-switch two-step confirmation flow, the `slowapi` rate limiter. All of these are referenced by this track's runbooks and dashboard queries.
- **`public_surface` track landed** — the `POST /engine/v1/public/abuse/report` endpoint lives under the public router prefix, inheriting the anonymous rate limit tier.

### Soft dependencies

- **`agent_identity` track landed** — the runbook's "ban a misbehaving agent" section assumes `POST /api/v1/identity/agents/{name}/revoke` exists. Without `agent_identity`, the only granularity is "kill-switch everything" or "rotate the master API key."
- **`intelligence_memory` structured logging** — the `log_event()` framework produces the events that Sentry alert rules key on.
- **Grafana instance** — provisioned separately (not in scope). The dashboard JSON in §C assumes Grafana exists and has Prometheus/Loki data sources configured.

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Abuse report endpoint becomes a DoS vector (attackers flood reports) | Rate-limited via anonymous tier + an additional per-endpoint limit (1 report/minute per IP). Report body size capped at 5KB. |
| Reporter PII exposed in `audit_logs` | Reporter IP stored as `sha256(ip + salt)`, not plaintext. Reporter-provided contact is optional; if supplied, stored as-is with a spec note that it will be used only for follow-up. |
| Runbooks go stale as the system changes | Quarterly review reminder in CLAUDE.md "Always do" ("re-read runbooks every 90 days"); follow-up PR adds a CI check that fails if runbooks haven't been touched in > 180 days. |
| Kill-switch operations runbook describes a procedure that doesn't match the actual code | Integration test in `trading/tests/integration/test_kill_switch_runbook.py` that **executes** the runbook's curl commands against a test server and asserts the documented behavior. If the code changes, the test fails. |
| Sentry alert rules never get configured in practice (the operator ships the doc but never wires the alerts) | The runbook includes a one-line "I have configured these alerts" checkbox for the operator to tick on first setup. Not enforceable via code, but surfaces the gap. |
| Grafana dashboard drift (panels query columns that don't exist after schema changes) | Dashboard JSON is versioned in git under `docs/grafana/`; PR reviews catch schema-panel mismatches. |
| Incident response depends on operator being available — single point of failure | Out of scope for this track. Multi-operator handoff requires SOC-level infrastructure we're explicitly not building. Documented limitation. |

## 7. Quality Gates

- [ ] **Abuse report endpoint works** — unit test submits a report via `TestClient`, verifies it lands in `incident.abuse_reports` with the correct category, status defaults to `new`, and the response includes a `report_id`.
- [ ] **Anonymous reporting works** — same test without auth headers; verifies the report is accepted, `reporter_name` is `"anonymous"`, `reporter_ip_hash` is populated.
- [ ] **Report body size limit enforced** — test with a 10KB body; expects 422.
- [ ] **Invalid category rejected** — test with `category: "not-a-category"`; expects 422.
- [ ] **High-severity categories emit Sentry alerts** — test with `category: "security"`; mock `capture_message`; verifies it was called.
- [ ] **Migration applies cleanly** — integration test verifies `incident.abuse_reports` table exists after migration.
- [ ] **Kill-switch runbook integration test** — executes the runbook's curl commands against a test server and asserts the documented behavior.
- [ ] **All runbooks present** — pytest globs `docs/runbooks/` for the 5 required files and asserts they exist:
  - `docs/runbooks/incident-response.md`
  - `docs/runbooks/kill-switch-operations.md`
  - `docs/runbooks/abuse-contact.md`
  - `docs/runbooks/post-incident-review-template.md`
  - `docs/runbooks/sentry-alerts.md`
- [ ] **Grafana dashboard JSON validates** — test parses `docs/grafana/agent-observability.json` and asserts it's valid JSON with the required top-level keys.

## 8. Out of scope / future work

- **Provisioning a Grafana instance** — infrastructure setup, not defensive perimeter
- **On-call rotation / PagerDuty integration** — single-operator assumption
- **Automated remediation** — no auto-ban, no auto-quarantine
- **ML anomaly detection** — no model training, no inference on incoming traffic
- **Public status page** — `GET /engine/v1/public/status` covers this at v1
- **Threat intelligence feeds** — no blocklists, no IP reputation
- **Per-agent reputation scoring** — interesting idea for v2
- **Abuse report triage workflow UI** — v1 triages via direct SQL (`SELECT * FROM incident.abuse_reports WHERE status = 'new'`)
- **Automated incident report creation** — post-incident review is manual, copy-paste from template
- **Compliance documentation** (SOC 2, GDPR, etc.) — separate track
- **Honeypot endpoints** — endpoints that look sensitive but exist to catch abuse. Interesting for v2.
- **Automated post-incident analysis** — running log diffs through an LLM to surface what went wrong. Stretch goal.

## 9. References

- Audit: `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- This track's audit cross-ref: `conductor/tracks/abuse_response/audit-cross-ref.md`
- Sibling tracks (all hard or soft dependencies): `defensive_perimeter`, `agent_identity`, `public_surface`, `intelligence_memory`, `moltbook_publisher`
- Memory: `reference_agent_readiness_audit.md`, `reference_moltbook.md` (especially the Moltbook breach history), `feedback_parallel_opencode_stream.md` (coordination with parallel agent streams)
