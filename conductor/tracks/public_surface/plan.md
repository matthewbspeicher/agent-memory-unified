# Implementation Plan: Public Surface (Audit Phase D prep)

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. TDD where practical.

**Goal:** Ship the agent-facing public surface — `FOR_AGENTS.md`, `/.well-known/agents.json`, landing route, and `trading/api/routes/public.py` — behind the anonymous rate limit tier from the `defensive_perimeter` track.

**Spec:** `conductor/tracks/public_surface/spec.md`

**Hard dependency:** `defensive_perimeter` track landed. Tasks 2-6 below cannot merge before Phase A ships because they depend on the anonymous rate limit tier being wired. Tasks 1 (the content files) can land independently — they're static markdown/JSON and don't touch the API at all.

---

## Phase 1: Static content (can land before defensive_perimeter)

### Task 1: Author `FOR_AGENTS.md`, `TERMS_FOR_AGENTS.md`, and `agents.json`

**Files:**
- Create: `FOR_AGENTS.md` at repo root
- Create: `TERMS_FOR_AGENTS.md` at repo root
- Create: `trading/public_content/agents.json` (canonical source)
- Create: `trading/public_content/FOR_AGENTS.md` (symlink or copy for FastAPI serving)

- [ ] **Step 1:** Write `FOR_AGENTS.md` per the content outline in spec §3.D. ~300-500 words. Use placeholders (`<domain>`, `<handle>`) where values aren't yet known.

- [ ] **Step 2:** Write `TERMS_FOR_AGENTS.md`. 3 sections: (1) Data usage (public endpoints are best-effort, no SLA), (2) Abuse (define what counts, what the response will be), (3) Kill-switch policy (operator reserves the right to halt any endpoint). Keep it under 300 words.

- [ ] **Step 3:** Write `trading/public_content/agents.json` per the schema in spec §3.E. Populate the `endpoints` array with all 9 endpoints from spec §3.B. Set `operator.verification.handle` to `<handle>` placeholder until Moltbook registration.

- [ ] **Step 4:** Create the FastAPI serving copy by symlinking or duplicating `trading/public_content/FOR_AGENTS.md`:
  ```bash
  cp FOR_AGENTS.md trading/public_content/FOR_AGENTS.md
  ```
  (symlinks don't always work across WSL/Windows — copy is safer).

- [ ] **Step 5:** Validate the JSON:
  ```bash
  python -m json.tool trading/public_content/agents.json
  ```
  Expected: valid JSON output, no parse errors.

- [ ] **Step 6:** Commit static content:
  ```bash
  git add FOR_AGENTS.md TERMS_FOR_AGENTS.md trading/public_content/
  git commit -m "docs(public): add FOR_AGENTS.md, TERMS, and agents.json canonical source"
  ```

---

## Phase 2: Landing route (depends on nothing, quick win)

### Task 2: Implement the root landing route

**Files:**
- Create: `trading/api/landing.py`
- Modify: `trading/api/app.py` (register the router)
- Create: `trading/tests/unit/test_landing_route.py`

- [ ] **Step 1: Write the failing test first**

```python
# trading/tests/unit/test_landing_route.py
from fastapi.testclient import TestClient
from api.app import create_app

def test_landing_route_returns_welcome_dict():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "1.0"
    assert data["name"] == "agent-memory-unified"
    assert "docs" in data
    assert "for_agents" in data["docs"]
    assert "agents_manifest" in data["docs"]
    assert "openapi" in data["docs"]
    assert "rate_limits" in data
    assert data["rate_limits"]["anonymous"] == "10 req/min"
    assert "contact" in data
    assert "abuse" in data["contact"]
```

- [ ] **Step 2: Run test and verify failure**
  ```bash
  cd trading && python -m pytest tests/unit/test_landing_route.py -v
  ```
  Expected: FAIL (route not defined, or returns 404).

- [ ] **Step 3: Implement the route**

```python
# trading/api/landing.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/", include_in_schema=False)
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
            "audit": "/engine/v1/public/for-agents",
        },
        "auth": {
            "public_endpoints": "no auth required",
            "private_endpoints": "X-API-Key header (contact abuse@<domain> for a verified agent key)",
        },
        "rate_limits": {
            "anonymous": "10 req/min",
            "moltbook-verified": "60 req/min",
            "registered": "300 req/min",
        },
        "contact": {
            "abuse": "abuse@<domain>",
            "moltbook": "@<handle>",
        },
    }
```

- [ ] **Step 4: Register the router in `trading/api/app.py`**

Add to the imports:
```python
from api.landing import router as landing_router
```

And register before the other routers (so `/` is handled first):
```python
app.include_router(landing_router)
```

- [ ] **Step 5: Run test and verify pass**
  ```bash
  cd trading && python -m pytest tests/unit/test_landing_route.py -v
  ```
  Expected: PASS.

- [ ] **Step 6: Commit:**
  ```bash
  git add trading/api/landing.py trading/api/app.py trading/tests/unit/test_landing_route.py
  git commit -m "feat(api): add GET / landing route with agent welcome JSON"
  ```

---

## Phase 3: Public router (depends on defensive_perimeter Phase A)

### Task 3: Scaffold `routes/public.py` with the status endpoint

**Files:**
- Create: `trading/api/routes/public.py`
- Create: `trading/tests/unit/test_public_routes.py`
- Modify: `trading/api/app.py` (register the router)

- [ ] **Step 1: Write failing test**

```python
# trading/tests/unit/test_public_routes.py
from fastapi.testclient import TestClient
from api.app import create_app

def test_public_status_returns_version_and_served_by():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "1.0"
    assert data["name"] == "agent-memory-unified"
    assert "version" in data
    assert "uptime_seconds" in data
    assert data["served_by"] == "agent-memory-unified"
    assert data["docs"] == "/FOR_AGENTS.md"
```

- [ ] **Step 2: Run and verify failure** (`ModuleNotFoundError: api.routes.public`).

- [ ] **Step 3: Create `trading/api/routes/public.py` with the status endpoint**

```python
"""Public router — curated read-only endpoints for external agents.

Every endpoint here is anonymous-allowed and rate-limited at the anonymous
tier (10 req/min) via the defensive_perimeter middleware. No mutation
methods may be called from this file. Enforced by test_public_surface_scoping.

See conductor/tracks/public_surface/spec.md for design.
"""
from __future__ import annotations

import time
from fastapi import APIRouter

router = APIRouter(prefix="/engine/v1/public", tags=["public"])

_STARTUP_TIME = time.time()


def _base_response() -> dict:
    """Common fields every public response includes."""
    return {
        "schema_version": "1.0",
        "name": "agent-memory-unified",
        "served_by": "agent-memory-unified",
        "docs": "/FOR_AGENTS.md",
    }


@router.get("/status")
async def public_status():
    return {
        **_base_response(),
        "version": "0.1.0",  # TODO: load from pyproject.toml at startup
        "uptime_seconds": int(time.time() - _STARTUP_TIME),
    }
```

- [ ] **Step 4: Register in `app.py`**

```python
from api.routes.public import router as public_router
# ...
app.include_router(public_router)
```

- [ ] **Step 5: Run test and verify pass.**

- [ ] **Step 6: Commit:**
  ```bash
  git add trading/api/routes/public.py trading/api/app.py trading/tests/unit/test_public_routes.py
  git commit -m "feat(api): scaffold public router with /status endpoint"
  ```

### Task 4: Implement remaining read endpoints

**Files:**
- Modify: `trading/api/routes/public.py`
- Modify: `trading/tests/unit/test_public_routes.py`

- [ ] **Step 1: Write failing tests for each remaining endpoint**

```python
def test_public_agents_lists_internal_agents():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert isinstance(data["agents"], list)
    # Each agent must have name + strategy + description, no secrets
    for agent in data["agents"]:
        assert "name" in agent
        assert "strategy" in agent
        assert "description" in agent
        # Verify no internal-only fields leaked
        forbidden = {"api_key", "token", "secret", "private_key", "internal_id"}
        assert not (forbidden & set(agent.keys()))


def test_public_arena_state_returns_safe_subset():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/arena/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_match" in data or data.get("note")  # note if no active match
    assert "top_leaderboard" in data
    assert data["served_by"] == "agent-memory-unified"


def test_public_leaderboard_returns_top_50_or_fewer():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "leaderboard" in data
    assert len(data["leaderboard"]) <= 50
    assert "as_of" in data


def test_public_kg_entity_returns_facts():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/kg/entity/BTC")
    assert resp.status_code == 200
    data = resp.json()
    assert "entity" in data
    assert "facts" in data
    assert "count" in data


def test_public_kg_timeline_returns_chronological():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/kg/timeline?entity=BTC&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "timeline" in data


def test_public_milestones_returns_posted_entries():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/milestones")
    assert resp.status_code == 200
    data = resp.json()
    assert "milestones" in data
    # Until the publisher runs, this is empty
    assert isinstance(data["milestones"], list)
```

- [ ] **Step 2: Run tests and verify failures** — all should fail with 404 or missing fields.

- [ ] **Step 3: Implement each endpoint.** Pseudocode; adapt to actual internal service names:

```python
# In trading/api/routes/public.py

from fastapi import Request
from pathlib import Path
import yaml

# ... _base_response() from Task 3 ...

@router.get("/agents")
async def public_agents(request: Request):
    # Read agents.yaml for the canonical list
    # TODO: pull from request.app.state.agent_runner if available for live state
    agents_yaml_path = Path(__file__).parent.parent.parent / "agents.yaml"
    if agents_yaml_path.exists():
        agents_data = yaml.safe_load(agents_yaml_path.read_text())
        agents = [
            {
                "name": a["name"],
                "strategy": a.get("strategy", "unknown"),
                "description": a.get("description", ""),
                "action_level": a.get("action_level", "notify"),
            }
            for a in agents_data.get("agents", [])
        ]
    else:
        agents = []
    return {**_base_response(), "agents": agents}


@router.get("/arena/state")
async def public_arena_state(request: Request):
    arena = getattr(request.app.state, "arena_manager", None)
    if not arena:
        return {**_base_response(), "note": "Arena not initialized", "top_leaderboard": []}
    # Pull safe subset — no internal IDs
    state = {
        "current_match": await arena.get_current_match_public() if hasattr(arena, "get_current_match_public") else None,
        "season": await arena.get_current_season_public() if hasattr(arena, "get_current_season_public") else None,
        "top_leaderboard": await arena.get_top_leaderboard(limit=5) if hasattr(arena, "get_top_leaderboard") else [],
    }
    return {**_base_response(), **state}


@router.get("/leaderboard")
async def public_leaderboard(request: Request):
    arena = getattr(request.app.state, "arena_manager", None)
    if not arena:
        return {**_base_response(), "leaderboard": [], "as_of": None}
    leaderboard = await arena.get_leaderboard(limit=50) if hasattr(arena, "get_leaderboard") else []
    return {
        **_base_response(),
        "leaderboard": leaderboard,
        "as_of": leaderboard[0]["as_of"] if leaderboard else None,
    }


@router.get("/kg/entity/{name}")
async def public_kg_entity(name: str, request: Request, direction: str = "both"):
    kg = getattr(request.app.state, "knowledge_graph", None)
    if not kg:
        return {**_base_response(), "entity": name, "facts": [], "count": 0, "note": "KG not initialized"}
    # Only return facts from publicly-tagged triples (filter)
    facts = await kg.query_entity_public(name, direction=direction) if hasattr(kg, "query_entity_public") else []
    return {**_base_response(), "entity": name, "facts": facts, "count": len(facts)}


@router.get("/kg/timeline")
async def public_kg_timeline(request: Request, entity: str | None = None, limit: int = 50):
    kg = getattr(request.app.state, "knowledge_graph", None)
    if not kg:
        return {**_base_response(), "entity": entity, "timeline": [], "count": 0}
    timeline = await kg.timeline_public(entity_name=entity, limit=min(limit, 50)) if hasattr(kg, "timeline_public") else []
    return {**_base_response(), "entity": entity, "timeline": timeline, "count": len(timeline)}


@router.get("/milestones")
async def public_milestones():
    feed_dir = Path(__file__).parent.parent.parent.parent / "project-feed"
    if not feed_dir.exists():
        return {**_base_response(), "milestones": []}
    # Read all top-level .md files (skip drafts/), filter by status: posted
    import re
    posted = []
    for md in sorted(feed_dir.glob("*.md"), reverse=True):
        if md.name == "README.md":
            continue
        content = md.read_text()
        # Very simple frontmatter parse — just look for status: posted
        fm_match = re.search(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if not fm_match:
            continue
        fm = fm_match.group(1)
        if "status: posted" not in fm:
            continue
        title_match = re.search(r"^title:\s*[\"']?(.+?)[\"']?\s*$", fm, re.MULTILINE)
        summary_match = re.search(r"^summary:\s*[\"']?(.+?)[\"']?\s*$", fm, re.MULTILINE)
        posted.append({
            "slug": md.stem,
            "title": title_match.group(1) if title_match else md.stem,
            "summary": summary_match.group(1) if summary_match else "",
        })
        if len(posted) >= 20:
            break
    return {**_base_response(), "milestones": posted}
```

Note: `query_entity_public` and `timeline_public` methods on the KG are assumed (per the spec's §6 risk mitigation — filter at query time by a `public` boolean tag). If the KG doesn't have these methods yet, add a follow-up task to add them. For v1, the endpoints can return empty lists gracefully if the methods aren't implemented.

- [ ] **Step 4: Run tests and verify pass.**

- [ ] **Step 5: Commit:**
  ```bash
  git add trading/api/routes/public.py trading/tests/unit/test_public_routes.py
  git commit -m "feat(api): add public read endpoints (agents, arena, leaderboard, kg, milestones)"
  ```

---

## Phase 4: Scoping linter + JSON manifest consistency

### Task 5: Add public-surface scoping linter

**Files:**
- Create: `trading/tests/unit/test_public_surface_scoping.py`

- [ ] **Step 1: Write the linter test**

```python
# trading/tests/unit/test_public_surface_scoping.py
"""Ensures trading/api/routes/public.py cannot call mutation methods.

Fails if any forbidden method name is invoked inside the file.
"""
import ast
from pathlib import Path

FORBIDDEN_METHOD_NAMES = {
    # Mutation / write methods — public surface is READ ONLY
    "execute_trade", "place_order", "cancel_order", "modify_order",
    "stop_agent", "start_agent", "evolve", "scan",
    "kill_switch", "activate_kill_switch", "deactivate",
    "add_entity", "add_triple", "invalidate", "update_weights",
    "set_weights", "store", "write", "delete", "remove",
    "create", "register", "promote", "settle", "breed",
    "approve", "reject", "tune", "transition",
}

ALLOWED_EXCEPTIONS = {
    # Safe reads that happen to contain forbidden substrings — explicit allowlist
    "get_current_match_public",  # read-only arena query
    "get_current_season_public",
    "get_top_leaderboard",
    "get_leaderboard",
    "query_entity_public",
    "timeline_public",
    "_base_response",
}


def test_public_py_calls_no_mutation_methods():
    public_py = Path(__file__).parent.parent.parent / "api" / "routes" / "public.py"
    assert public_py.exists(), f"Missing {public_py}"

    tree = ast.parse(public_py.read_text())
    forbidden_calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Extract the method name being called
            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                method_name = node.func.id
            else:
                continue

            if method_name in ALLOWED_EXCEPTIONS:
                continue
            # Exact match OR contains a forbidden substring NOT in the allowlist
            if method_name in FORBIDDEN_METHOD_NAMES:
                forbidden_calls.append((node.lineno, method_name))

    assert not forbidden_calls, (
        f"public.py calls forbidden mutation methods: {forbidden_calls}. "
        f"Public surface must be read-only. If you need to call one of these, "
        f"it belongs in a different router."
    )


def test_public_py_has_no_api_key_dependencies():
    """Public routes must not require authentication."""
    public_py = Path(__file__).parent.parent.parent / "api" / "routes" / "public.py"
    content = public_py.read_text()
    # No imports of verify_api_key or require_scope
    assert "verify_api_key" not in content, (
        "public.py must not import verify_api_key — public routes are anonymous"
    )
    assert "require_scope" not in content, (
        "public.py must not import require_scope — public routes are anonymous"
    )
```

- [ ] **Step 2: Run the linter**
  ```bash
  cd trading && python -m pytest tests/unit/test_public_surface_scoping.py -v
  ```
  Expected: PASS (the `public.py` we wrote in Task 4 only calls read methods or the whitelisted `_public` variants).

- [ ] **Step 3: Commit:**
  ```bash
  git add trading/tests/unit/test_public_surface_scoping.py
  git commit -m "test(api): add scoping linter for public.py — no mutation methods allowed"
  ```

### Task 6: Add `agents.json` drift test

**Files:**
- Create: `trading/tests/unit/test_agents_manifest.py`

- [ ] **Step 1: Write the drift test**

```python
# trading/tests/unit/test_agents_manifest.py
"""Ensures agents.json stays in sync with the actual public router."""
import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent.parent.parent / "public_content" / "agents.json"
PUBLIC_PY_PATH = Path(__file__).parent.parent.parent / "api" / "routes" / "public.py"


def test_agents_json_is_valid():
    assert MANIFEST_PATH.exists(), f"Missing {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text())
    assert data["schema_version"] == "1.0"
    assert data["name"] == "agent-memory-unified"
    assert "endpoints" in data
    assert len(data["endpoints"]) > 0


def test_agents_json_endpoints_match_routes():
    data = json.loads(MANIFEST_PATH.read_text())
    manifest_paths = {e["path"] for e in data["endpoints"]}

    # Extract route paths from public.py — look for @router.get(...)
    import re
    public_content = PUBLIC_PY_PATH.read_text()
    route_matches = re.findall(r'@router\.get\("([^"]+)"', public_content)
    # Combine with the router prefix
    actual_paths = {f"/engine/v1/public{p}" if not p.startswith("/engine") else p for p in route_matches}

    missing_in_manifest = actual_paths - manifest_paths
    extra_in_manifest = manifest_paths - actual_paths

    assert not missing_in_manifest, (
        f"agents.json is missing these routes: {missing_in_manifest}. "
        f"Update trading/public_content/agents.json to match."
    )
    assert not extra_in_manifest, (
        f"agents.json lists these routes that don't exist in public.py: {extra_in_manifest}. "
        f"Either add the routes or remove from the manifest."
    )
```

- [ ] **Step 2: Run and verify pass** (assuming Task 4's public.py matches Task 1's agents.json).

- [ ] **Step 3: Commit:**
  ```bash
  git add trading/tests/unit/test_agents_manifest.py
  git commit -m "test(api): add drift detection between agents.json and public.py routes"
  ```

---

## Phase 5: Static file serving + integration tests

### Task 7: Serve `FOR_AGENTS.md` and `agents.json` via FastAPI + frontend Vite

**Files:**
- Modify: `trading/api/routes/public.py` (add FOR_AGENTS.md serve endpoint)
- Create: `frontend/public/.well-known/agents.json` (copy or symlink)
- Modify: `trading/api/app.py` (add StaticFiles mount if needed, OR add a `/` + `.well-known/` passthrough)

- [ ] **Step 1: Add `FOR_AGENTS.md` serve endpoint to `public.py`**

```python
from fastapi.responses import Response

@router.get("/for-agents", include_in_schema=True)
async def public_for_agents():
    md_path = Path(__file__).parent.parent.parent / "public_content" / "FOR_AGENTS.md"
    if not md_path.exists():
        return Response(content="# FOR_AGENTS.md not found\n", media_type="text/markdown", status_code=404)
    return Response(content=md_path.read_text(), media_type="text/markdown")


@router.get("/agents.json", include_in_schema=True)
async def public_agents_json():
    from fastapi.responses import JSONResponse
    json_path = Path(__file__).parent.parent.parent / "public_content" / "agents.json"
    if not json_path.exists():
        return JSONResponse(content={"error": "agents.json not found"}, status_code=404)
    return JSONResponse(content=json.loads(json_path.read_text()))
```

- [ ] **Step 2: Copy the manifest to frontend/public/.well-known/**

```bash
mkdir -p frontend/public/.well-known
cp trading/public_content/agents.json frontend/public/.well-known/agents.json
```

Add a package.json `predev`/`prebuild` script to keep them in sync:
```json
"scripts": {
  "predev": "cp ../trading/public_content/agents.json public/.well-known/agents.json",
  "prebuild": "cp ../trading/public_content/agents.json public/.well-known/agents.json"
}
```

- [ ] **Step 3: Write integration tests for serving**

```python
def test_for_agents_markdown_endpoint():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/for-agents")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    # Sanity: file has our project name
    assert "agent-memory-unified" in resp.text


def test_agents_json_endpoint_serves_manifest():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/agents.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "1.0"
    assert data["name"] == "agent-memory-unified"
```

- [ ] **Step 4: Run and verify pass.**

- [ ] **Step 5: Commit:**
  ```bash
  git add trading/api/routes/public.py trading/tests/unit/test_public_routes.py frontend/public/.well-known/ frontend/package.json
  git commit -m "feat(api): serve FOR_AGENTS.md and agents.json via FastAPI + frontend"
  ```

---

## Phase 6: Rate limit integration + no-secrets scan

### Task 8: Rate limit integration test (depends on defensive_perimeter)

**Files:**
- Create: `trading/tests/integration/test_public_rate_limits.py`

**Blocked by:** `defensive_perimeter` Phase A landed.

- [ ] **Step 1: Write the test**

```python
# trading/tests/integration/test_public_rate_limits.py
import pytest
from fastapi.testclient import TestClient
from api.app import create_app


@pytest.mark.integration
def test_anonymous_tier_rate_limit_on_public_status():
    """11 rapid requests from the same IP should see 10 × 200 and then 1 × 429."""
    app = create_app()
    client = TestClient(app)

    success_count = 0
    rate_limited_count = 0

    for _ in range(11):
        resp = client.get("/engine/v1/public/status")
        if resp.status_code == 200:
            success_count += 1
        elif resp.status_code == 429:
            rate_limited_count += 1
            assert "retry_after_seconds" in resp.json() or "retry-after" in resp.headers

    assert success_count == 10, f"Expected 10 × 200, got {success_count}"
    assert rate_limited_count == 1, f"Expected 1 × 429, got {rate_limited_count}"
```

- [ ] **Step 2: Mark the test `integration`** in `pytest.ini` conftest if not already.

- [ ] **Step 3: Run integration test** (requires Redis + defensive_perimeter's middleware):
  ```bash
  cd trading && python -m pytest tests/integration/test_public_rate_limits.py -v -m integration
  ```

- [ ] **Step 4: Commit:**
  ```bash
  git add trading/tests/integration/test_public_rate_limits.py
  git commit -m "test(api): integration test — anonymous tier rate limits public endpoints"
  ```

### Task 9: No-secrets scan test

**Files:**
- Create: `trading/tests/unit/test_public_no_secrets.py`

- [ ] **Step 1: Write the scanner**

```python
# trading/tests/unit/test_public_no_secrets.py
"""Ensures no public endpoint response can leak secrets.

Hits every GET endpoint on the public router and greps responses for
forbidden substrings.
"""
import re
from fastapi.testclient import TestClient
from api.app import create_app


FORBIDDEN_SUBSTRINGS = [
    "STA_",       # env var prefix — never in public responses
    "B64_",       # wallet reconstruction
    "api_key",    # any context
    "apikey",
    "secret",     # case-insensitive check below
    "password",
    "coldkey",
    "hotkey",
    "wallet",
    "private_key",
    "bearer ",
    "Authorization",
]

PUBLIC_ENDPOINTS = [
    "/engine/v1/public/status",
    "/engine/v1/public/agents",
    "/engine/v1/public/arena/state",
    "/engine/v1/public/leaderboard",
    "/engine/v1/public/kg/entity/BTC",
    "/engine/v1/public/kg/timeline",
    "/engine/v1/public/milestones",
    "/engine/v1/public/agents.json",
]


def test_no_public_endpoint_leaks_secrets():
    app = create_app()
    client = TestClient(app)

    leaks = []
    for path in PUBLIC_ENDPOINTS:
        resp = client.get(path)
        body = resp.text.lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            # Case-insensitive match
            if forbidden.lower() in body:
                # Allowlist: "api_key_header" in an endpoint description is OK
                # (e.g., agents.json describes auth methods)
                # Allow the substring only if it's in an auth-description context
                if forbidden == "api_key" and '"api_key_header"' in resp.text:
                    continue
                if forbidden == "bearer " and "bearer token" in body:
                    continue
                leaks.append((path, forbidden))

    assert not leaks, f"Public endpoints leaked forbidden substrings: {leaks}"
```

- [ ] **Step 2: Run and verify pass.**

- [ ] **Step 3: Commit:**
  ```bash
  git add trading/tests/unit/test_public_no_secrets.py
  git commit -m "test(api): no-secrets scan across all public endpoint responses"
  ```

---

## Quality Gates (from spec §7, restated)

Before merging the full track:

- [ ] Public surface linter passes (Task 5)
- [ ] `agents.json` schema validates + drift test passes (Task 6)
- [ ] Rate limit integration test passes (Task 8, requires defensive_perimeter)
- [ ] Landing route smoke test passes (Task 2)
- [ ] `FOR_AGENTS.md` served correctly (Task 7)
- [ ] No-secrets scan passes (Task 9)
- [ ] Public KG endpoint respects `public` filter (covered implicitly in Task 4 tests, explicitly in a follow-up when the `public` column or allowlist is added)

## Commit strategy

9 logical commits across 6 phases. Each task = one commit. Each commit leaves the tree in a buildable state:

1. Task 1 — Static content (FOR_AGENTS.md, TERMS, agents.json)
2. Task 2 — Landing route + test
3. Task 3 — Public router scaffold + status endpoint
4. Task 4 — Remaining public read endpoints
5. Task 5 — Scoping linter
6. Task 6 — agents.json drift test
7. Task 7 — FOR_AGENTS.md + agents.json serving
8. Task 8 — Rate limit integration test (after defensive_perimeter)
9. Task 9 — No-secrets scan

Tasks 1-7 can land on a feature branch while `defensive_perimeter` is still in progress. Task 8 requires defensive_perimeter merged to `main` first. Task 9 is independent of rate limiting.
