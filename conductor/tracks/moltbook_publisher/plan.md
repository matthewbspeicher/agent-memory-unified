# Implementation Plan: Moltbook Publisher

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. TDD where practical.

**Goal:** Ship `scripts/publish-to-moltbook.py` with frontmatter parsing, secret scanning, rate-limit awareness, and human-in-the-loop publishing. No automated runs; default dry-run; explicit `--yes` required to POST.

**Spec:** `conductor/tracks/moltbook_publisher/spec.md`

**Dependencies:** None of the *implementation* tasks depend on other tracks. Full end-to-end test (Task 11) depends on a real or mocked Moltbook API. Actually publishing (not a task in this plan, but the ultimate use) depends on the human Moltbook registration step.

---

## Phase 1: Frontmatter parsing + round-trip

### Task 1: Frontmatter reader with body preservation

**Files:**
- Create: `scripts/moltbook_frontmatter.py`
- Create: `scripts/tests/fixtures/valid-post.md`
- Create: `scripts/tests/test_moltbook_frontmatter.py`

- [ ] **Step 1: Create fixture**

```markdown
<!-- scripts/tests/fixtures/valid-post.md -->
---
title: "Test post"
summary: "A one-sentence summary"
tags: [test, fixture]
submolt_targets: [m/test]
status: ready
posted_to_moltbook: false
posted_at: null
post_uuid: null
source_links:
  - type: spec
    url: docs/test-spec.md
---

This is the body.

Multiple paragraphs should be preserved byte-for-byte.
```

- [ ] **Step 2: Write failing test**

```python
# scripts/tests/test_moltbook_frontmatter.py
from pathlib import Path
import pytest
from moltbook_frontmatter import read_post, write_post_frontmatter, Post

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_read_valid_post():
    post = read_post(FIXTURE_DIR / "valid-post.md")
    assert post.title == "Test post"
    assert post.summary == "A one-sentence summary"
    assert post.tags == ["test", "fixture"]
    assert post.submolt_targets == ["m/test"]
    assert post.status == "ready"
    assert post.posted_to_moltbook is False
    assert post.posted_at is None
    assert post.post_uuid is None
    assert len(post.source_links) == 1
    assert post.source_links[0]["type"] == "spec"
    assert "This is the body." in post.body
    assert "Multiple paragraphs" in post.body


def test_round_trip_preserves_body_bytes(tmp_path):
    source = FIXTURE_DIR / "valid-post.md"
    target = tmp_path / "valid-post-copy.md"
    target.write_bytes(source.read_bytes())
    post = read_post(target)
    write_post_frontmatter(
        target,
        updates={
            "status": "posted",
            "posted_to_moltbook": True,
            "posted_at": "2026-04-15T14:32:11+00:00",
            "post_uuid": "test-uuid-123",
        },
    )
    rewritten = read_post(target)
    assert rewritten.status == "posted"
    assert rewritten.posted_to_moltbook is True
    assert rewritten.post_uuid == "test-uuid-123"
    # Body must be unchanged byte-for-byte
    original_body = source.read_text().split("---\n", 2)[-1]
    rewritten_body = target.read_text().split("---\n", 2)[-1]
    assert original_body == rewritten_body
```

- [ ] **Step 3: Run test, verify failure**

```bash
cd scripts && python -m pytest tests/test_moltbook_frontmatter.py -v
```

Expected: FAIL (module not found).

- [ ] **Step 4: Implement**

```python
# scripts/moltbook_frontmatter.py
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


@dataclass
class Post:
    path: Path
    title: str
    summary: str
    tags: list[str]
    submolt_targets: list[str]
    status: str
    posted_to_moltbook: bool
    posted_at: str | None
    post_uuid: str | None
    source_links: list[dict]
    body: str
    raw_frontmatter: dict = field(default_factory=dict)


_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def read_post(path: Path) -> Post:
    """Parse a project-feed/*.md file into a Post."""
    text = path.read_text(encoding="utf-8")
    match = _FM_RE.match(text)
    if not match:
        raise ValueError(f"{path}: no YAML frontmatter found at start of file")
    fm_text = match.group(1)
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{path}: malformed YAML frontmatter: {e}")
    body = text[match.end():]
    return Post(
        path=path,
        title=fm.get("title", ""),
        summary=fm.get("summary", ""),
        tags=list(fm.get("tags", [])),
        submolt_targets=list(fm.get("submolt_targets", [])),
        status=fm.get("status", "draft"),
        posted_to_moltbook=bool(fm.get("posted_to_moltbook", False)),
        posted_at=fm.get("posted_at"),
        post_uuid=fm.get("post_uuid"),
        source_links=list(fm.get("source_links", [])),
        body=body,
        raw_frontmatter=fm,
    )


def write_post_frontmatter(path: Path, *, updates: dict[str, Any]) -> None:
    """Rewrite just the frontmatter block of a post file.

    The body is preserved byte-for-byte. `updates` is merged into the existing
    frontmatter (shallow merge; keys in `updates` overwrite).
    """
    text = path.read_text(encoding="utf-8")
    match = _FM_RE.match(text)
    if not match:
        raise ValueError(f"{path}: no frontmatter to update")
    fm = yaml.safe_load(match.group(1)) or {}
    fm.update(updates)
    new_fm_text = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).rstrip("\n")
    new_text = f"---\n{new_fm_text}\n---\n" + text[match.end():]
    path.write_text(new_text, encoding="utf-8")
```

- [ ] **Step 5: Run test, verify pass**

```bash
cd scripts && python -m pytest tests/test_moltbook_frontmatter.py -v
```

- [ ] **Step 6: Commit**

```bash
git add scripts/moltbook_frontmatter.py scripts/tests/test_moltbook_frontmatter.py scripts/tests/fixtures/valid-post.md
git commit -m "feat(moltbook): add frontmatter reader with body-preserving round-trip"
```

---

## Phase 2: Secret scanner

### Task 2: Secret scanner with fixture coverage

**Files:**
- Create: `scripts/moltbook_secret_scan.py`
- Create: `scripts/tests/fixtures/secret-leak.md`
- Create: `scripts/tests/test_secret_scan.py`

- [ ] **Step 1: Create secret-leak fixture**

```markdown
<!-- scripts/tests/fixtures/secret-leak.md -->
---
title: "Bad post with secrets"
summary: "Don't post this"
tags: [test]
submolt_targets: [m/test]
status: ready
posted_to_moltbook: false
---

Here's our config:
```
STA_API_KEY=sk-abc123def456
B64_HOTKEY=eyJ0eXAiOiJKV1Qi
```

And a bearer token: bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
```

- [ ] **Step 2: Write failing test**

```python
# scripts/tests/test_secret_scan.py
from pathlib import Path
import pytest
from moltbook_secret_scan import scan, SecretFound

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_clean_text_passes():
    clean = "This is a perfectly clean post about design systems and tailwind tokens."
    scan(clean)  # should not raise


def test_sta_env_var_detected():
    bad = "Here's our config: STA_API_KEY=sk-abc123def456"
    with pytest.raises(SecretFound) as exc:
        scan(bad)
    assert "STA_" in exc.value.reason


def test_b64_wallet_var_detected():
    bad = "Setting B64_HOTKEY=eyJ0eXAiOiJKV1Qi for verification"
    with pytest.raises(SecretFound):
        scan(bad)


def test_bearer_token_detected():
    bad = "Authorization: bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9xyz123"
    with pytest.raises(SecretFound):
        scan(bad)


def test_pem_private_key_detected():
    bad = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA..."
    with pytest.raises(SecretFound):
        scan(bad)


def test_postgres_connection_string_with_credentials_detected():
    bad = "Connection: postgres://user:password@host/db"
    with pytest.raises(SecretFound):
        scan(bad)


def test_secret_leak_fixture_rejected():
    content = (FIXTURE_DIR / "secret-leak.md").read_text()
    with pytest.raises(SecretFound):
        scan(content)
```

- [ ] **Step 3: Run test, verify failures**

- [ ] **Step 4: Implement**

```python
# scripts/moltbook_secret_scan.py
from __future__ import annotations
import re
from dataclasses import dataclass


FORBIDDEN_PATTERNS = [
    (r"STA_[A-Z_]+\s*=", "STA_ env var assignment"),
    (r"B64_(COLDKEY|HOTKEY)", "Bittensor wallet reconstruction var"),
    (r"(?i)api[_-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{10,}", "api key literal"),
    (r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer token"),
    (r"(?i)\b(password|passwd)\s*[:=]\s*['\"]?[^\s'\"]{4,}", "password assignment"),
    (r"(?i)\bsecret\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{8,}", "secret assignment"),
    (r"-----BEGIN .*PRIVATE KEY-----", "PEM private key"),
    (r"postgres(ql)?://[^@\s]+:[^@\s]+@", "Postgres connection string with credentials"),
    (r"redis://[^@\s]*:[^@\s]+@", "Redis connection string with credentials"),
    (r"mongodb(\+srv)?://[^@\s]+:[^@\s]+@", "Mongo connection string with credentials"),
]


@dataclass
class SecretFound(Exception):
    reason: str
    line: int
    snippet: str

    def __str__(self) -> str:
        return f"secret detected ({self.reason}) at line {self.line}: {self.snippet[:80]}..."


def scan(text: str) -> None:
    """Scan text for forbidden patterns. Raises SecretFound on any hit."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, reason in FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                raise SecretFound(reason=reason, line=lineno, snippet=line)
```

- [ ] **Step 5: Run test, verify pass**

- [ ] **Step 6: Commit**

```bash
git add scripts/moltbook_secret_scan.py scripts/tests/test_secret_scan.py scripts/tests/fixtures/secret-leak.md
git commit -m "feat(moltbook): add secret scanner with 10 forbidden patterns"
```

---

## Phase 3: Rate-limit state persistence

### Task 3: Local state file persistence

**Files:**
- Create: `scripts/moltbook_state.py`
- Create: `scripts/tests/test_moltbook_state.py`
- Modify: `.gitignore` (add `scripts/.moltbook-state.json`)

- [ ] **Step 1: Update `.gitignore`**

```bash
echo "scripts/.moltbook-state.json" >> .gitignore
```

- [ ] **Step 2: Write failing test**

```python
# scripts/tests/test_moltbook_state.py
from datetime import datetime, timezone
from pathlib import Path
import time
import pytest
from moltbook_state import load_state, save_state, check_rate_limit, RateLimitExhausted


def test_fresh_state_has_no_last_post(tmp_path):
    state_file = tmp_path / "state.json"
    state = load_state(state_file)
    assert state["last_post"] is None
    assert state["rate_limit"]["remaining"] is None


def test_save_and_reload(tmp_path):
    state_file = tmp_path / "state.json"
    state = load_state(state_file)
    state["last_post"] = {
        "uuid": "abc123",
        "submolt": "m/test",
        "title": "Test",
        "posted_at": "2026-04-15T14:00:00+00:00",
        "source_file": "project-feed/test.md",
    }
    state["rate_limit"] = {
        "limit": 2,
        "remaining": 1,
        "reset_epoch": int(time.time()) + 1800,
        "updated_at": "2026-04-15T14:00:00+00:00",
    }
    save_state(state_file, state)

    reloaded = load_state(state_file)
    assert reloaded["last_post"]["uuid"] == "abc123"
    assert reloaded["rate_limit"]["remaining"] == 1


def test_rate_limit_check_passes_when_remaining_positive(tmp_path):
    state_file = tmp_path / "state.json"
    state = load_state(state_file)
    state["rate_limit"] = {
        "limit": 2,
        "remaining": 1,
        "reset_epoch": int(time.time()) + 1800,
        "updated_at": "now",
    }
    check_rate_limit(state)  # should not raise


def test_rate_limit_check_refuses_when_exhausted(tmp_path):
    state_file = tmp_path / "state.json"
    state = load_state(state_file)
    reset_in_1800s = int(time.time()) + 1800
    state["rate_limit"] = {
        "limit": 2,
        "remaining": 0,
        "reset_epoch": reset_in_1800s,
        "updated_at": "now",
    }
    with pytest.raises(RateLimitExhausted) as exc:
        check_rate_limit(state)
    assert exc.value.reset_epoch == reset_in_1800s


def test_rate_limit_check_allows_after_reset(tmp_path):
    state_file = tmp_path / "state.json"
    state = load_state(state_file)
    state["rate_limit"] = {
        "limit": 2,
        "remaining": 0,
        "reset_epoch": int(time.time()) - 60,  # reset was 1 min ago
        "updated_at": "old",
    }
    check_rate_limit(state)  # should not raise; the reset has passed
```

- [ ] **Step 3: Run test, verify failures**

- [ ] **Step 4: Implement**

```python
# scripts/moltbook_state.py
from __future__ import annotations
import json
import time
from pathlib import Path
from dataclasses import dataclass


SCHEMA_VERSION = "1.0"

DEFAULT_STATE = {
    "schema_version": SCHEMA_VERSION,
    "last_post": None,
    "rate_limit": {
        "limit": None,
        "remaining": None,
        "reset_epoch": None,
        "updated_at": None,
    },
    "agent": {
        "name": None,
        "profile_url": None,
    },
}


@dataclass
class RateLimitExhausted(Exception):
    reset_epoch: int
    remaining: int

    def __str__(self) -> str:
        from datetime import datetime, timezone
        reset_dt = datetime.fromtimestamp(self.reset_epoch, tz=timezone.utc)
        return (
            f"Rate limit exhausted (remaining={self.remaining}). "
            f"Next post allowed at {reset_dt.isoformat()}. "
            f"Use --force-post to override (not recommended)."
        )


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {**DEFAULT_STATE, "rate_limit": {**DEFAULT_STATE["rate_limit"]}, "agent": {**DEFAULT_STATE["agent"]}}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {**DEFAULT_STATE, "rate_limit": {**DEFAULT_STATE["rate_limit"]}, "agent": {**DEFAULT_STATE["agent"]}}
    # Ensure all keys exist even if the file is older
    for key, default in DEFAULT_STATE.items():
        data.setdefault(key, default)
    return data


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, sort_keys=False), encoding="utf-8")


def check_rate_limit(state: dict) -> None:
    """Raise RateLimitExhausted if the rate limit window disallows a new post."""
    rl = state.get("rate_limit", {})
    remaining = rl.get("remaining")
    reset_epoch = rl.get("reset_epoch")
    if remaining is None or reset_epoch is None:
        return  # no prior state, allow
    if remaining > 0:
        return
    now = int(time.time())
    if reset_epoch <= now:
        return  # window has reset
    raise RateLimitExhausted(reset_epoch=reset_epoch, remaining=remaining)
```

- [ ] **Step 5: Run test, verify pass**

- [ ] **Step 6: Commit**

```bash
git add scripts/moltbook_state.py scripts/tests/test_moltbook_state.py .gitignore
git commit -m "feat(moltbook): add rate-limit state persistence + gitignored state file"
```

---

## Phase 4: Moltbook API client

### Task 4: Thin HTTP client with mocked integration test

**Files:**
- Create: `scripts/moltbook_client.py`
- Create: `scripts/tests/test_moltbook_client.py`

- [ ] **Step 1: Write failing tests (using `httpx.MockTransport`)**

```python
# scripts/tests/test_moltbook_client.py
import pytest
import httpx
from moltbook_client import MoltbookClient, RateLimitError, MoltbookPost


def make_client(handler):
    transport = httpx.MockTransport(handler)
    client = MoltbookClient(api_key="test-key", base_url="https://www.moltbook.com")
    client._client = httpx.Client(
        base_url="https://www.moltbook.com",
        headers={"Authorization": "Bearer test-key"},
        transport=transport,
    )
    return client


def test_create_post_success():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        body = request.read().decode()
        assert "Test Title" in body
        assert "m/test" in body
        return httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "2",
                "X-RateLimit-Remaining": "1",
                "X-RateLimit-Reset": "1718476331",
            },
            json={
                "uuid": "post-uuid-123",
                "created_at": "2026-04-15T14:00:00Z",
            },
        )

    client = make_client(handler)
    post, rate = client.create_post(title="Test Title", body="Body text", submolt="m/test")
    assert post.uuid == "post-uuid-123"
    assert post.submolt == "m/test"
    assert post.url == "https://www.moltbook.com/post/post-uuid-123"
    assert rate.remaining == 1
    assert rate.reset_epoch == 1718476331


def test_create_post_rate_limited_raises_rate_limit_error():
    def handler(request):
        return httpx.Response(
            429,
            headers={"X-RateLimit-Reset": "1718476331"},
            json={"error": "rate limited"},
        )

    client = make_client(handler)
    with pytest.raises(RateLimitError) as exc:
        client.create_post(title="x", body="x", submolt="m/test")
    assert exc.value.retry_after == 1718476331


def test_create_post_server_error_raises_http_error():
    def handler(request):
        return httpx.Response(500, json={"error": "server error"})

    client = make_client(handler)
    with pytest.raises(httpx.HTTPStatusError):
        client.create_post(title="x", body="x", submolt="m/test")
```

- [ ] **Step 2: Run test, verify failure (module not found).**

- [ ] **Step 3: Implement** — use the full client from spec §3.D. Copy verbatim.

- [ ] **Step 4: Run test, verify pass.**

- [ ] **Step 5: Commit**

```bash
git add scripts/moltbook_client.py scripts/tests/test_moltbook_client.py
git commit -m "feat(moltbook): add httpx-based Moltbook API client with RateLimitError"
```

---

## Phase 5: Post body formatter

### Task 5: Format post body from frontmatter + markdown body

**Files:**
- Create: `scripts/moltbook_formatter.py`
- Create: `scripts/tests/test_moltbook_formatter.py`

- [ ] **Step 1: Write failing test**

```python
# scripts/tests/test_moltbook_formatter.py
from moltbook_formatter import format_post_body
from moltbook_frontmatter import Post
from pathlib import Path


def make_post(**overrides):
    defaults = dict(
        path=Path("test.md"),
        title="Test Title",
        summary="A one-sentence summary.",
        tags=["test"],
        submolt_targets=["m/test"],
        status="ready",
        posted_to_moltbook=False,
        posted_at=None,
        post_uuid=None,
        source_links=[],
        body="This is the body.\n\nMore paragraphs.",
        raw_frontmatter={},
    )
    defaults.update(overrides)
    return Post(**defaults)


def test_format_basic_post():
    post = make_post()
    body = format_post_body(post, agent_handle="test-agent")
    # Summary prepended (italicized)
    assert "_A one-sentence summary._" in body
    # Body preserved
    assert "This is the body." in body
    # Footer with handle
    assert "Posted via project-feed by @test-agent" in body


def test_format_with_source_links():
    post = make_post(
        source_links=[
            {"type": "spec", "url": "docs/spec.md"},
            {"type": "commits", "range": "abc123..def456"},
        ]
    )
    body = format_post_body(post, agent_handle="test-agent")
    assert "**Sources:**" in body
    assert "Spec: `docs/spec.md`" in body
    assert "Commits: `abc123..def456`" in body


def test_summary_not_duplicated_if_body_starts_with_it():
    post = make_post(
        summary="This is the body.",
        body="This is the body.\n\nMore paragraphs.",
    )
    body = format_post_body(post, agent_handle="test-agent")
    # Summary should NOT be prepended a second time
    lines = body.splitlines()
    italicized_count = sum(1 for l in lines if l.startswith("_") and l.endswith("_"))
    # Only the footer should be italicized (the "Posted via..." line)
    assert italicized_count <= 1
```

- [ ] **Step 2: Run test, verify failures.**

- [ ] **Step 3: Implement**

```python
# scripts/moltbook_formatter.py
from __future__ import annotations
from moltbook_frontmatter import Post


def format_post_body(post: Post, *, agent_handle: str) -> str:
    parts = []
    summary = post.summary.strip()
    body = post.body.strip()
    if summary and not body.startswith(summary):
        parts.append(f"_{summary}_")
        parts.append("")  # blank line
    parts.append(body)
    if post.source_links:
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append("**Sources:**")
        for link in post.source_links:
            link_type = str(link.get("type", "link")).capitalize()
            if link_type.lower() == "commits":
                val = link.get("range", link.get("url", ""))
            else:
                val = link.get("url", "")
            parts.append(f"- {link_type}: `{val}`")
    parts.append("")
    parts.append(f"_Posted via project-feed by @{agent_handle}_")
    return "\n".join(parts)
```

- [ ] **Step 4: Run test, verify pass.**

- [ ] **Step 5: Commit**

```bash
git add scripts/moltbook_formatter.py scripts/tests/test_moltbook_formatter.py
git commit -m "feat(moltbook): add post body formatter with summary + sources + footer"
```

---

## Phase 6: CLI entry point

### Task 6: Wire everything together in `publish-to-moltbook.py`

**Files:**
- Create: `scripts/publish-to-moltbook.py`
- Create: `scripts/tests/fixtures/already-posted.md`
- Create: `scripts/tests/test_publish_cli.py`

- [ ] **Step 1: Create the already-posted fixture**

```markdown
<!-- scripts/tests/fixtures/already-posted.md -->
---
title: "Already posted"
summary: "This post is already on Moltbook"
tags: [test]
submolt_targets: [m/test]
status: posted
posted_to_moltbook: true
posted_at: "2026-04-15T10:00:00+00:00"
post_uuid: previously-posted-uuid
---

Body content.
```

- [ ] **Step 2: Write CLI smoke test**

```python
# scripts/tests/test_publish_cli.py
import subprocess
import sys
from pathlib import Path
import pytest


SCRIPT = Path(__file__).parent.parent / "publish-to-moltbook.py"


def run(*args, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


def test_list_with_empty_feed_dir_prints_nothing_and_exits_zero(tmp_path):
    empty = tmp_path / "feed"
    empty.mkdir()
    result = run("list", "--feed-dir", str(empty))
    assert result.returncode == 0
    assert "no posts" in result.stdout.lower() or result.stdout.strip() == ""


def test_preview_of_valid_post_shows_formatted_body(tmp_path):
    feed = tmp_path / "feed"
    feed.mkdir()
    # Copy fixture
    fixture = Path(__file__).parent / "fixtures" / "valid-post.md"
    (feed / "valid-post.md").write_text(fixture.read_text())
    result = run("preview", str(feed / "valid-post.md"))
    assert result.returncode == 0
    assert "_A one-sentence summary._" in result.stdout
    assert "This is the body." in result.stdout


def test_publish_refuses_already_posted_file(tmp_path):
    feed = tmp_path / "feed"
    feed.mkdir()
    fixture = Path(__file__).parent / "fixtures" / "already-posted.md"
    (feed / "already-posted.md").write_text(fixture.read_text())
    result = run("publish", str(feed / "already-posted.md"), "--yes", "--dry-run")
    assert result.returncode != 0
    assert "already posted" in result.stdout.lower() or "already posted" in result.stderr.lower()


def test_publish_refuses_draft_status(tmp_path):
    feed = tmp_path / "feed"
    feed.mkdir()
    draft_content = """---
title: "Draft post"
summary: "Still drafting"
tags: [test]
submolt_targets: [m/test]
status: draft
posted_to_moltbook: false
---

Draft body.
"""
    (feed / "draft-post.md").write_text(draft_content)
    result = run("publish", str(feed / "draft-post.md"), "--yes", "--dry-run")
    assert result.returncode != 0
    assert "draft" in (result.stdout + result.stderr).lower()


def test_publish_refuses_secret_leak(tmp_path):
    feed = tmp_path / "feed"
    feed.mkdir()
    fixture = Path(__file__).parent / "fixtures" / "secret-leak.md"
    (feed / "secret-leak.md").write_text(fixture.read_text())
    # Change status to ready so it passes the first check and triggers the secret scan
    content = (feed / "secret-leak.md").read_text().replace("status: ready", "status: ready")
    (feed / "secret-leak.md").write_text(content)
    result = run("publish", str(feed / "secret-leak.md"), "--yes", "--dry-run")
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "secret" in combined or "forbidden" in combined
```

- [ ] **Step 3: Run test, verify failures.**

- [ ] **Step 4: Implement the CLI** — full ~200 lines covering all subcommands (`list`, `preview`, `publish`, `status`, `register-wizard`). Key elements:

```python
#!/usr/bin/env python3
"""Publish project-feed entries to Moltbook.

Default behavior is dry-run. Explicit --yes is required to actually POST.
Secret scanning, rate-limit awareness, and frontmatter round-tripping are
all enforced before any network call.

See conductor/tracks/moltbook_publisher/spec.md for design.
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Make sibling modules importable
sys.path.insert(0, str(Path(__file__).parent))

from moltbook_frontmatter import read_post, write_post_frontmatter, Post
from moltbook_secret_scan import scan as secret_scan, SecretFound
from moltbook_state import load_state, save_state, check_rate_limit, RateLimitExhausted
from moltbook_formatter import format_post_body


DEFAULT_FEED_DIR = Path(__file__).parent.parent / "project-feed"
DEFAULT_STATE_FILE = Path(__file__).parent / ".moltbook-state.json"
DEFAULT_ENV_FILE = Path(__file__).parent.parent / "trading" / ".env"


def load_api_key(env_file: Path) -> str | None:
    """Load MOLTBOOK_API_KEY from an env file or from os.environ."""
    key = os.environ.get("MOLTBOOK_API_KEY")
    if key:
        return key
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("MOLTBOOK_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def get_agent_handle_from_state(state: dict) -> str:
    return state.get("agent", {}).get("name") or "unknown-agent"


def cmd_list(args: argparse.Namespace) -> int:
    feed_dir = Path(args.feed_dir)
    posts = []
    for md in sorted(feed_dir.glob("*.md")):
        if md.name == "README.md":
            continue
        try:
            posts.append(read_post(md))
        except ValueError as e:
            print(f"  ⚠ {md.name}: {e}", file=sys.stderr)
    if not posts:
        print("No posts in feed directory (skipping README.md and drafts/).")
        return 0
    print(f"Found {len(posts)} post(s) in {feed_dir}:\n")
    for post in posts:
        marker = {
            "draft": "📝",
            "ready": "✅",
            "posted": "📢",
        }.get(post.status, "❓")
        print(f"  {marker} [{post.status:6s}] {post.path.name}")
        print(f"         title: {post.title}")
        if post.status == "posted" and post.post_uuid:
            print(f"         uuid: {post.post_uuid}")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    post = read_post(Path(args.file))
    state = load_state(Path(args.state_file))
    handle = get_agent_handle_from_state(state)
    body = format_post_body(post, agent_handle=handle)
    print(f"Title: {post.title}")
    print(f"Submolts: {', '.join(post.submolt_targets) or '(none)'}")
    print(f"Status: {post.status}")
    print("=" * 60)
    print(body)
    print("=" * 60)
    # Run secret scan in preview too, surface violations early
    try:
        secret_scan(body)
        print("✓ Secret scan passed.")
    except SecretFound as exc:
        print(f"⚠ Secret scan FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    post = read_post(Path(args.file))
    state = load_state(Path(args.state_file))

    # Guard rails
    if post.posted_to_moltbook:
        print(f"✗ {post.path.name} is already posted (uuid: {post.post_uuid}). Refusing.", file=sys.stderr)
        return 1
    if post.status != "ready":
        print(f"✗ {post.path.name} has status '{post.status}' (must be 'ready'). Refusing.", file=sys.stderr)
        return 1

    handle = get_agent_handle_from_state(state)
    body = format_post_body(post, agent_handle=handle)

    # Secret scan (always, regardless of --force-post unless explicit)
    try:
        secret_scan(body)
    except SecretFound as exc:
        print(f"✗ Secret scan FAILED: {exc}", file=sys.stderr)
        if not args.force_post:
            return 2
        print(f"⚠ --force-post set; proceeding despite secret match", file=sys.stderr)

    # Rate limit check
    try:
        check_rate_limit(state)
    except RateLimitExhausted as exc:
        print(f"✗ {exc}", file=sys.stderr)
        if not args.force_post:
            return 3
        print(f"⚠ --force-post set; bypassing rate limit", file=sys.stderr)

    # Always dry-run unless --yes AND not --dry-run
    if args.dry_run or not args.yes:
        print(f"\n--- DRY RUN (no network call) ---")
        print(f"Would post to: {', '.join(post.submolt_targets)}")
        print(f"Title: {post.title}")
        print(f"Body length: {len(body)} chars")
        if not args.yes:
            print("\nRun with --yes to actually post.")
        return 0

    # Real publish path
    api_key = load_api_key(Path(args.env_file))
    if not api_key:
        print(f"✗ MOLTBOOK_API_KEY not found in {args.env_file} or environment", file=sys.stderr)
        return 4

    from moltbook_client import MoltbookClient, RateLimitError
    client = MoltbookClient(api_key=api_key)

    successes = []
    partial = []
    for submolt in post.submolt_targets:
        try:
            mpost, rate = client.create_post(title=post.title, body=body, submolt=submolt)
            print(f"✓ Posted to {submolt}: {mpost.url}")
            successes.append({"uuid": mpost.uuid, "submolt": submolt, "url": mpost.url})
            # Update state after every success
            state["rate_limit"] = {
                "limit": rate.limit,
                "remaining": rate.remaining,
                "reset_epoch": rate.reset_epoch,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            save_state(Path(args.state_file), state)
        except RateLimitError as exc:
            print(f"✗ Rate limited on {submolt}: {exc}", file=sys.stderr)
            partial.append(submolt)
            break
        except Exception as exc:
            print(f"✗ Failed to post to {submolt}: {exc}", file=sys.stderr)
            partial.append(submolt)

    if successes:
        # Update frontmatter with first success
        first = successes[0]
        updates = {
            "status": "posted",
            "posted_to_moltbook": True,
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "post_uuid": first["uuid"],
        }
        if partial:
            updates["partial_cross_post"] = True
            updates["unposted_targets"] = partial
        write_post_frontmatter(post.path, updates=updates)

        # Update last_post in state
        state["last_post"] = {
            "uuid": first["uuid"],
            "submolt": first["submolt"],
            "title": post.title,
            "posted_at": updates["posted_at"],
            "source_file": str(post.path),
        }
        save_state(Path(args.state_file), state)
        return 0 if not partial else 5
    return 6


def cmd_status(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state_file))
    print(f"Agent: {state.get('agent', {}).get('name') or '(not registered)'}")
    print(f"Profile: {state.get('agent', {}).get('profile_url') or '(none)'}")
    print(f"Last post: {state.get('last_post') or '(none)'}")
    print(f"Rate limit: {state.get('rate_limit')}")
    return 0


def cmd_register_wizard(args: argparse.Namespace) -> int:
    print("Moltbook agent registration wizard (manual walkthrough)")
    print("=" * 60)
    print()
    print("This wizard cannot automate registration — Twitter verification")
    print("is a manual step. Follow the instructions below.")
    print()
    print("See conductor/tracks/moltbook_publisher/spec.md §3.H for the full")
    print("9-step walkthrough. Abbreviated version:")
    print()
    print("  1. Open https://www.moltbook.com/")
    print("  2. Read https://www.moltbook.com/skill.md")
    print("  3. Register at /developers with name + description")
    print("  4. Copy the API key (shown ONCE)")
    print("  5. Paste into trading/.env as MOLTBOOK_API_KEY=...")
    print("  6. Follow claim URL → email verification")
    print("  7. Post the verification tweet on X")
    print("  8. Confirm the claim on Moltbook")
    print("  9. Run: python scripts/publish-to-moltbook.py status")
    print()
    print("Return here when done and run `status` to verify.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--feed-dir", default=str(DEFAULT_FEED_DIR))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Show all project-feed entries with status")

    p_preview = sub.add_parser("preview", help="Format and print a post, no network")
    p_preview.add_argument("file")

    p_publish = sub.add_parser("publish", help="Post to Moltbook (default dry-run)")
    p_publish.add_argument("file")
    p_publish.add_argument("--yes", action="store_true", help="skip interactive confirmation")
    p_publish.add_argument("--dry-run", action="store_true", help="force dry-run (default)")
    p_publish.add_argument("--force-post", action="store_true", help="bypass secret scan + rate limit")

    sub.add_parser("status", help="Show agent status + last post + rate limit window")

    sub.add_parser("register-wizard", help="Interactive walkthrough of human registration steps")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "list": cmd_list,
        "preview": cmd_preview,
        "publish": cmd_publish,
        "status": cmd_status,
        "register-wizard": cmd_register_wizard,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests, verify pass.**

- [ ] **Step 6: Commit**

```bash
git add scripts/publish-to-moltbook.py scripts/tests/test_publish_cli.py scripts/tests/fixtures/already-posted.md
git commit -m "feat(moltbook): add CLI entry point with list/preview/publish/status/register-wizard subcommands"
```

---

## Phase 7: Supporting files

### Task 7: Update `.env.example` and document the publisher

**Files:**
- Modify: `trading/.env.example` (add `MOLTBOOK_API_KEY`)
- Create: `scripts/README.md` (or update if exists)

- [ ] **Step 1: Add MOLTBOOK_API_KEY to .env.example**

```bash
# Append to trading/.env.example
echo "" >> trading/.env.example
echo "# Moltbook publisher (scripts/publish-to-moltbook.py)" >> trading/.env.example
echo "# Obtain by running: python scripts/publish-to-moltbook.py register-wizard" >> trading/.env.example
echo "MOLTBOOK_API_KEY=" >> trading/.env.example
```

- [ ] **Step 2: Document in scripts/README.md**

```markdown
# scripts/

## publish-to-moltbook.py

Publishes project-feed/*.md entries to Moltbook. Default dry-run.

Quick reference:
- `list` — show all entries with status
- `preview <file>` — format and print, no network
- `publish <file>` — POST to Moltbook (needs --yes)
- `status` — check agent + rate limit
- `register-wizard` — manual registration walkthrough

See `conductor/tracks/moltbook_publisher/spec.md` for the full spec.

State file: `scripts/.moltbook-state.json` (gitignored).
API key: `trading/.env` as `MOLTBOOK_API_KEY=...` (gitignored).
```

- [ ] **Step 3: Commit**

```bash
git add trading/.env.example scripts/README.md
git commit -m "docs(moltbook): add MOLTBOOK_API_KEY to .env.example and scripts/README.md"
```

---

## Quality gates (from spec §7)

Before merging the full track:

- [ ] Frontmatter round-trip preserves body bytes (Task 1)
- [ ] Secret scanner catches all 10 forbidden patterns (Task 2)
- [ ] Rate limit state refuses when exhausted, allows after reset (Task 3)
- [ ] HTTP client handles 200/429/5xx correctly (Task 4)
- [ ] Post body formatter doesn't duplicate summary (Task 5)
- [ ] CLI refuses already-posted files, draft files, and secret-leak fixtures (Task 6)
- [ ] `MOLTBOOK_API_KEY` placeholder in `.env.example` (Task 7)
- [ ] All tests pass with `cd scripts && python -m pytest tests/ -v`

## Commit strategy

**7 logical commits**, each task = one commit. Every commit leaves the publisher in a testable state (the CLI just isn't functional until Task 6). Tasks 1-5 can land in any order; Task 6 depends on Tasks 1-5; Task 7 is independent.
