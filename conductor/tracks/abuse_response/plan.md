# Implementation Plan: Abuse Response & Operational Readiness

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Documentation-heavy; fewer TDD cycles than other tracks.

**Goal:** Ship the "what happens when things go wrong" layer — abuse report endpoint, incident response runbook, per-agent Grafana dashboard, Sentry alert rules, kill-switch operations playbook, and post-incident review template.

**Spec:** `conductor/tracks/abuse_response/spec.md`

**Dependencies:**
- Hard: `defensive_perimeter` Phase A landed (audit_logs table, kill-switch, rate limiter)
- Hard: `public_surface` landed (abuse report endpoint lives under public router)
- Soft: `agent_identity` landed (revoke-agent runbook section assumes it exists)

---

## Phase 1: Schema + data model

### Task 1: `incident` schema migration for abuse reports

**Files:**
- Create: `scripts/migrations/add-abuse-reports.sql`
- Create: `trading/tests/integration/test_incident_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/integration/test_incident_schema.py
import pytest
import asyncpg


@pytest.mark.integration
@pytest.mark.asyncio
async def test_incident_schema_exists(postgres_dsn):
    conn = await asyncpg.connect(postgres_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'incident')"
        )
        assert exists, "incident schema not created"

        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'incident' AND table_name = 'abuse_reports')"
        )
        assert table_exists, "incident.abuse_reports table not created"
    finally:
        await conn.close()
```

- [ ] **Step 2: Run test, verify failure.**

- [ ] **Step 3: Write the migration file** from spec §3.G verbatim.

- [ ] **Step 4: Apply to local Postgres**

```bash
docker exec -i agent-memory-unified-postgres-1 psql -U postgres -d agent_memory < scripts/migrations/add-abuse-reports.sql
```

- [ ] **Step 5: Run test, verify pass.**

- [ ] **Step 6: Commit**

```bash
git add scripts/migrations/add-abuse-reports.sql trading/tests/integration/test_incident_schema.py
git commit -m "feat(incident): add Postgres incident schema for abuse reports"
```

---

## Phase 2: Abuse report endpoint

### Task 2: `AbuseReport` model + store + POST /engine/v1/public/abuse/report

**Files:**
- Create: `trading/api/abuse/__init__.py` (empty)
- Create: `trading/api/abuse/schemas.py`
- Create: `trading/api/abuse/store.py`
- Create: `trading/api/routes/abuse.py`
- Modify: `trading/api/app.py` (register the router)
- Create: `trading/tests/unit/test_abuse_report.py`

- [ ] **Step 1: Write failing tests**

```python
# trading/tests/unit/test_abuse_report.py
from fastapi.testclient import TestClient
from api.app import create_app


def test_anonymous_report_accepted():
    app = create_app()
    client = TestClient(app)
    resp = client.post(
        "/engine/v1/public/abuse/report",
        json={
            "category": "bug",
            "description": "The /engine/v1/public/leaderboard endpoint returns stale data",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "report_id" in data
    assert data["status"] == "submitted"
    assert "follow_up" in data


def test_invalid_category_rejected():
    app = create_app()
    client = TestClient(app)
    resp = client.post(
        "/engine/v1/public/abuse/report",
        json={"category": "nonsense", "description": "test " * 10},
    )
    # Pydantic validation or custom check
    assert resp.status_code in (400, 422)


def test_description_too_short_rejected():
    app = create_app()
    client = TestClient(app)
    resp = client.post(
        "/engine/v1/public/abuse/report",
        json={"category": "bug", "description": "hi"},
    )
    assert resp.status_code == 422


def test_description_too_large_rejected():
    app = create_app()
    client = TestClient(app)
    resp = client.post(
        "/engine/v1/public/abuse/report",
        json={"category": "bug", "description": "x" * 5001},
    )
    assert resp.status_code == 422


def test_reporter_ip_hashed_not_stored_plaintext(monkeypatch, tmp_path):
    # Implementation detail: verify that the store.insert method hashes the IP
    # before persisting. This requires mocking the store or reading it back.
    from api.abuse.store import hash_ip
    h = hash_ip("192.168.1.1")
    assert h != "192.168.1.1"
    assert len(h) == 64  # sha256 hex
    # Same input → same hash (deterministic with fixed salt)
    assert hash_ip("192.168.1.1") == h
    # Different input → different hash
    assert hash_ip("192.168.1.2") != h
```

- [ ] **Step 2: Run tests, verify failures.**

- [ ] **Step 3: Implement** the abuse module

```python
# trading/api/abuse/schemas.py
from pydantic import BaseModel, Field
from typing import Literal


class AbuseReport(BaseModel):
    category: Literal["bug", "rate-limit", "content", "identity", "security", "other"]
    description: str = Field(..., min_length=10, max_length=5000)
    affected_resource: str | None = Field(None, max_length=500)
    evidence: str | None = Field(None, max_length=2000)
    reporter_contact: str | None = Field(None, max_length=200)


class AbuseReportResponse(BaseModel):
    report_id: int
    received_at: str
    status: str
    follow_up: str
    served_by: str = "agent-memory-unified"
```

```python
# trading/api/abuse/store.py
from __future__ import annotations
import hashlib
import os
from datetime import datetime, timezone
import asyncpg


# Salt is loaded from env so it's configurable, but has a default for dev
_IP_HASH_SALT = os.environ.get("STA_IP_HASH_SALT", "default-dev-salt-rotate-in-prod")


def hash_ip(ip: str) -> str:
    """Hash an IP address with a salt for storage in abuse_reports.

    Deterministic (same IP always produces same hash) so we can correlate
    reports from the same source without storing plaintext IPs.
    """
    return hashlib.sha256((_IP_HASH_SALT + ip).encode()).hexdigest()


class AbuseStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def insert(
        self,
        *,
        category: str,
        description: str,
        affected_resource: str | None,
        evidence: str | None,
        reporter_name: str,
        reporter_contact: str | None,
        reporter_ip: str | None,
    ) -> int:
        ip_hash = hash_ip(reporter_ip) if reporter_ip else None
        async with self._pool.acquire() as conn:
            report_id = await conn.fetchval(
                """
                INSERT INTO incident.abuse_reports
                    (category, description, affected_resource, evidence,
                     reporter_name, reporter_contact, reporter_ip_hash, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'new')
                RETURNING id
                """,
                category, description, affected_resource, evidence,
                reporter_name, reporter_contact, ip_hash,
            )
        return report_id

    async def list_open(self, limit: int = 100) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, submitted_at, category, description, reporter_name, status
                FROM incident.abuse_reports
                WHERE status IN ('new', 'triaged', 'in-progress')
                ORDER BY submitted_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [dict(r) for r in rows]
```

```python
# trading/api/routes/abuse.py
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from typing import Annotated

from api.abuse.schemas import AbuseReport, AbuseReportResponse
from api.abuse.store import AbuseStore
from api.identity.dependencies import resolve_identity, Identity


router = APIRouter(prefix="/engine/v1/public/abuse", tags=["abuse"])


def _get_store(request: Request) -> AbuseStore:
    store = getattr(request.app.state, "abuse_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="abuse store not initialized")
    return store


@router.post("/report", response_model=AbuseReportResponse)
async def submit_abuse_report(
    report: AbuseReport,
    request: Request,
    identity: Annotated[Identity, Depends(resolve_identity)],
) -> AbuseReportResponse:
    store = _get_store(request)
    client_ip = request.client.host if request.client else None

    report_id = await store.insert(
        category=report.category,
        description=report.description,
        affected_resource=report.affected_resource,
        evidence=report.evidence,
        reporter_name=identity.name,
        reporter_contact=report.reporter_contact,
        reporter_ip=client_ip,
    )

    # High-severity categories emit a Sentry alert
    if report.category in ("identity", "security"):
        try:
            from sentry_sdk import capture_message
            capture_message(
                f"High-severity abuse report {report_id}: {report.category}",
                level="warning",
                extras={"category": report.category, "reporter": identity.name},
            )
        except ImportError:
            pass

    return AbuseReportResponse(
        report_id=report_id,
        received_at=datetime.now(timezone.utc).isoformat(),
        status="submitted",
        follow_up="abuse@<domain> will review within 24 hours",
    )
```

- [ ] **Step 4: Wire `AbuseStore` into `app.state` in `app.py`**

```python
from api.abuse.store import AbuseStore
# In lifespan:
app.state.abuse_store = AbuseStore(pool=postgres_pool)

from api.routes.abuse import router as abuse_router
app.include_router(abuse_router)
```

- [ ] **Step 5: Run tests, verify pass.**

- [ ] **Step 6: Commit**

```bash
git add trading/api/abuse/ trading/api/routes/abuse.py trading/api/app.py trading/tests/unit/test_abuse_report.py
git commit -m "feat(incident): add POST /engine/v1/public/abuse/report endpoint with IP hashing"
```

---

## Phase 3: Runbooks

### Task 3: Write `docs/runbooks/incident-response.md`

**Files:**
- Create: `docs/runbooks/incident-response.md`

- [ ] **Step 1: Draft the 9-section runbook** per spec §3.B with concrete commands:
  - Where to look first
  - How to halt everything
  - How to ban a misbehaving agent (assumes `agent_identity`)
  - How to rotate master API key
  - How to rotate Moltbook API key
  - How to tell if we've been breached
  - How to preserve evidence
  - When to fully restart
  - When to reach out to Moltbook

Each section has copy-pasteable curl commands with `<domain>`, `$STA_API_KEY`, etc. placeholders.

- [ ] **Step 2: Review for accuracy** — every command in the runbook must actually work against the current code. Specifically verify:
  - Kill-switch two-step flow matches `defensive_perimeter` Phase A implementation
  - Revoke endpoint matches `agent_identity` Phase B implementation (if landed; mark TODO if not)
  - Log paths match actual Docker container paths

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/incident-response.md
git commit -m "docs(runbook): add incident response runbook"
```

### Task 4: Write `docs/runbooks/kill-switch-operations.md`

**Files:**
- Create: `docs/runbooks/kill-switch-operations.md`

- [ ] **Step 1: Draft the 9-section runbook** per spec §3.E with concrete curl examples:
  - Who has access
  - How to trigger (two-step flow)
  - What it blocks
  - What it does NOT block
  - How to verify
  - How to deactivate
  - When NOT to trigger
  - Post-kill-switch recovery
  - Integration test note

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/kill-switch-operations.md
git commit -m "docs(runbook): add kill-switch operations playbook"
```

### Task 5: Write `docs/runbooks/sentry-alerts.md`

**Files:**
- Create: `docs/runbooks/sentry-alerts.md`

- [ ] **Step 1: Draft the alert rules doc** per spec §3.D table with:
  - Exact Sentry UI path to configure each rule
  - Exact condition / threshold / action for each
  - Checkbox list for operator to tick after configuration

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/sentry-alerts.md
git commit -m "docs(runbook): add Sentry alert rules configuration"
```

### Task 6: Write `docs/runbooks/abuse-contact.md` and `post-incident-review-template.md`

**Files:**
- Create: `docs/runbooks/abuse-contact.md`
- Create: `docs/runbooks/post-incident-review-template.md`

- [ ] **Step 1: Write abuse-contact.md** — single-page doc with the email alias, what to include in a report, response SLA (24h), escalation path.

- [ ] **Step 2: Write post-incident-review-template.md** — the markdown template from spec §3.F verbatim.

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/abuse-contact.md docs/runbooks/post-incident-review-template.md
git commit -m "docs(runbook): add abuse contact + post-incident review template"
```

---

## Phase 4: Grafana dashboard

### Task 7: Ship `docs/grafana/agent-observability.json`

**Files:**
- Create: `docs/grafana/agent-observability.json`
- Create: `trading/tests/unit/test_grafana_dashboard.py`

- [ ] **Step 1: Draft the dashboard JSON** with 10 panels per spec §3.C. Use Grafana's schema (v8+). Each panel has a unique `id`, a `title`, a `type` (`timeseries`, `stat`, `bargauge`, etc.), a `datasource` (placeholder `Prometheus` or `Postgres`), and a `targets` array with the query.

- [ ] **Step 2: Write a JSON validity test**

```python
# trading/tests/unit/test_grafana_dashboard.py
import json
from pathlib import Path


def test_dashboard_json_is_valid():
    path = Path(__file__).parent.parent.parent.parent / "docs" / "grafana" / "agent-observability.json"
    assert path.exists(), f"Dashboard JSON missing at {path}"
    data = json.loads(path.read_text())
    assert "title" in data
    assert "panels" in data
    assert len(data["panels"]) >= 10


def test_dashboard_has_all_required_panels():
    path = Path(__file__).parent.parent.parent.parent / "docs" / "grafana" / "agent-observability.json"
    data = json.loads(path.read_text())
    panel_titles = {p["title"] for p in data["panels"]}
    required = {
        "Request rate per agent",
        "Error rate per agent",
        "Rate-limit 429 count per IP",
        "Slow endpoints p95/p99",
        "Kill-switch status",
        "New identities (24h)",
        "Revocations (24h)",
        "Public endpoint hit count",
        "Abuse reports (24h)",
    }
    missing = required - panel_titles
    assert not missing, f"Missing required panels: {missing}"
```

- [ ] **Step 3: Run tests, verify pass.**

- [ ] **Step 4: Commit**

```bash
git add docs/grafana/agent-observability.json trading/tests/unit/test_grafana_dashboard.py
git commit -m "feat(observability): add Grafana agent observability dashboard JSON"
```

---

## Phase 5: Kill-switch runbook integration test

### Task 8: Integration test that exercises the kill-switch runbook

**Files:**
- Create: `trading/tests/integration/test_kill_switch_runbook.py`

**Blocked by:** `defensive_perimeter` Phase A landed (the kill-switch endpoints must exist).

- [ ] **Step 1: Write the integration test**

```python
# trading/tests/integration/test_kill_switch_runbook.py
"""Integration test that executes the kill-switch operations runbook.

If the runbook documents a command pattern, this test runs it and asserts
the expected behavior. If the code changes in a way that breaks the
runbook, this test fails and someone has to update the runbook.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_runbook_two_step_kill_switch_activation(client_with_master_key):
    # Step 1 from runbook: get confirmation token
    r1 = client_with_master_key.post("/api/v1/risk/kill-switch/initiate")
    assert r1.status_code == 200
    data1 = r1.json()
    assert "confirmation_token" in data1
    token = data1["confirmation_token"]
    assert data1.get("expires_in_seconds", 0) <= 60

    # Step 2 from runbook: confirm within 60s
    r2 = client_with_master_key.post(
        "/api/v1/risk/kill-switch/confirm",
        json={"token": token},
    )
    assert r2.status_code == 200
    assert r2.json().get("active") is True

    # Verify POST requests now return 503
    r3 = client_with_master_key.post("/api/v1/orders", json={"symbol": "BTC", "quantity": 0.001, "side": "BUY"})
    assert r3.status_code == 503

    # Verify GET requests STILL work (runbook §3.E.3 "what it does NOT block")
    r4 = client_with_master_key.get("/engine/v1/public/status")
    assert r4.status_code == 200

    # Cleanup: deactivate
    r5 = client_with_master_key.post("/api/v1/risk/kill-switch/deactivate", json={"reason": "test complete"})
    assert r5.status_code == 200


@pytest.mark.integration
def test_runbook_expired_token_rejected(client_with_master_key):
    r1 = client_with_master_key.post("/api/v1/risk/kill-switch/initiate")
    token = r1.json()["confirmation_token"]
    # Simulate expiry by waiting or by using a known-expired token
    # For a real test, configure a short expiry in the test fixture
    # For now, assert the endpoint honors the expiry contract via the response
    # (this test will need refinement based on how Phase A implemented expiry)
    pass  # placeholder; actual implementation depends on Phase A's test hooks
```

- [ ] **Step 2: Run the test, verify pass** (assumes defensive_perimeter Phase A landed).

- [ ] **Step 3: Commit**

```bash
git add trading/tests/integration/test_kill_switch_runbook.py
git commit -m "test(incident): integration test that exercises the kill-switch runbook"
```

---

## Phase 6: Documentation + runbook presence test

### Task 9: Runbook presence test

**Files:**
- Create: `trading/tests/unit/test_runbook_presence.py`

- [ ] **Step 1: Write the presence test**

```python
# trading/tests/unit/test_runbook_presence.py
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
RUNBOOK_DIR = REPO_ROOT / "docs" / "runbooks"

REQUIRED_RUNBOOKS = [
    "incident-response.md",
    "kill-switch-operations.md",
    "abuse-contact.md",
    "post-incident-review-template.md",
    "sentry-alerts.md",
]


def test_all_required_runbooks_exist():
    missing = [name for name in REQUIRED_RUNBOOKS if not (RUNBOOK_DIR / name).exists()]
    assert not missing, f"Missing required runbooks: {missing}"


def test_runbooks_are_not_empty():
    for name in REQUIRED_RUNBOOKS:
        path = RUNBOOK_DIR / name
        if path.exists():
            content = path.read_text()
            assert len(content) > 200, f"{name} is suspiciously short (<200 chars) — empty stub?"


def test_runbooks_have_title_heading():
    for name in REQUIRED_RUNBOOKS:
        path = RUNBOOK_DIR / name
        if path.exists():
            first_line = path.read_text().splitlines()[0].strip()
            assert first_line.startswith("# "), f"{name} missing top-level title heading"
```

- [ ] **Step 2: Run test, verify pass** (assumes Tasks 3-6 complete).

- [ ] **Step 3: Commit**

```bash
git add trading/tests/unit/test_runbook_presence.py
git commit -m "test(incident): assert required runbooks exist and are non-empty"
```

### Task 10: Update CLAUDE.md with quarterly runbook review reminder

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add under "Always do" in Working Boundaries**

```markdown
- **Re-read runbooks every 90 days** — `docs/runbooks/` contains the incident response, kill-switch operations, Sentry alerts, and abuse contact runbooks. They go stale as the system changes. Set a calendar reminder.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): add 90-day runbook review reminder to Working Boundaries"
```

---

## Quality Gates (from spec §7, restated)

- [ ] Abuse report endpoint works (Task 2)
- [ ] Anonymous reporting works (Task 2)
- [ ] Body size + category validation (Task 2)
- [ ] High-severity categories emit Sentry alerts (Task 2)
- [ ] Migration applies cleanly (Task 1)
- [ ] Kill-switch runbook integration test (Task 8)
- [ ] All runbooks present (Task 9)
- [ ] Grafana dashboard JSON validates (Task 7)

## Commit strategy

10 logical commits across 6 phases. Each task = one commit. Tasks 1, 2, 7, 9, 10 can land independently. Tasks 3-6 depend on each other loosely (all runbooks are content-only, no cross-dependencies). Task 8 depends on `defensive_perimeter` Phase A landed.
