# Specification: Moltbook Publisher

## 1. Objective

Implement the human-in-the-loop publisher script that takes markdown milestones from `project-feed/` and posts them to Moltbook (the agent social network) with rate-limit awareness, secret scanning, and frontmatter round-tripping. This is **work stream ε** from the Moltbook integration plan in `reference_moltbook.md`.

The core design principle is **nothing publishes without a human in the loop.** Default mode is dry-run (preview, no network). Explicit `--publish` + confirmation is required to actually POST. Rate limits are respected defensively. Post UUIDs are written back to the source file's frontmatter so the round-trip is traceable in git.

## 2. Non-goals

- **Automated posting.** No cron, no CI trigger, no webhook. Human runs the script, reviews the preview, confirms, and the post goes out. Automation is a post-v1 consideration after enough manual runs have built confidence.
- **Bidirectional sync.** This track is write-only. Reading comments, replies, or upvotes from Moltbook back into the repo is out of scope — `reference_moltbook.md` documents that Moltbook has no webhooks, so any sync would require polling which we're explicitly not building.
- **Multi-brand / multi-agent posting.** The publisher posts on behalf of **one** Moltbook agent identity (whoever `MOLTBOOK_API_KEY` authenticates as). Supporting multiple identities is deferred.
- **Rich media.** Text + link posts only, per the Moltbook API. No image uploads, no threaded posting, no comments.
- **Content authoring.** The publisher does not generate content — that's the job of `project-feed/` draft files. The publisher is a deterministic serializer: markdown file in → Moltbook post out.
- **Identity federation (consuming Moltbook identities for *our* API).** That's a separate piece of `reference_moltbook.md` work stream ε and belongs in the `agent_identity` or a dedicated federation track later.

## 3. Architecture & Design

### A. CLI interface

```
scripts/publish-to-moltbook.py [COMMAND] [OPTIONS]

Commands:
  list                      Show all project-feed entries with their publication status
  preview <file>            Format and print the post as it would appear on Moltbook, no network
  publish <file>            Post to Moltbook (default: dry-run; requires --yes to actually POST)
  status                    Check Moltbook agent status, last post timestamp, rate limit window
  register-wizard           Interactive walkthrough of the human registration steps (does NOT automate Twitter)

Options:
  --yes                     Skip interactive confirmation (use with --publish for scripted runs)
  --dry-run                 Force dry-run even with --yes (default behavior; explicit override)
  --verbose                 Diagnostic logging
  --env-file PATH           Path to .env file with MOLTBOOK_API_KEY (default: trading/.env)
  --feed-dir PATH           Path to project-feed/ (default: project-feed/)
  --state-file PATH         Path to local state JSON (default: scripts/.moltbook-state.json)
  --force-post              Bypass rate-limit check (dangerous; logged loudly)
```

**Default behavior for `publish` without `--yes`:** print the preview, ask "Post to Moltbook submolts [m/foo, m/bar]? [y/N]", require explicit `y`. Press Ctrl-C to abort cleanly.

**Default behavior for `publish` with `--yes`:** skip the prompt but still print the preview and a summary before the network call.

### B. File structure

```
scripts/
├── publish-to-moltbook.py         # main CLI entry point
├── moltbook_client.py             # thin wrapper around Moltbook REST API
├── moltbook_state.py              # local state persistence (last post, rate limit)
└── .moltbook-state.json           # GITIGNORED — persists rate limit state + last post UUID

scripts/tests/
├── fixtures/
│   ├── valid-post.md              # well-formed project-feed entry
│   ├── secret-leak.md             # fixture with secrets; publisher MUST reject
│   ├── malformed-frontmatter.md   # invalid YAML; publisher MUST reject
│   └── already-posted.md          # frontmatter says posted_to_moltbook: true; publisher MUST skip
├── test_publish_to_moltbook.py    # unit tests for the publisher
├── test_moltbook_client.py        # unit tests for the API wrapper
├── test_moltbook_state.py         # unit tests for state persistence
└── test_secret_scan.py            # unit tests for the secret scanner

trading/
└── .env.example                   # MODIFIED — adds MOLTBOOK_API_KEY placeholder

.gitignore                         # MODIFIED — adds scripts/.moltbook-state.json
```

### C. Frontmatter parsing + round-tripping

The publisher reads each `project-feed/*.md` file (skipping `drafts/`), parses YAML frontmatter between `---` delimiters, and extracts:

| Field | Purpose |
|---|---|
| `title` | Moltbook post title |
| `summary` | Appended to the body as the opening paragraph if the body doesn't already start with it |
| `tags` | Mapped to Moltbook post tags if the API supports them (verify at implementation time) |
| `submolt_targets` | List of submolts to cross-post to; one POST per submolt (respecting rate limits across the set) |
| `status` | Must be `ready` (not `draft` or `posted`) for the publisher to proceed |
| `posted_to_moltbook` | Must be `false`; `true` means already posted, skip |
| `source_links` | Used to build the post body's "Sources" section at the bottom |

On successful post:
- `status` → `posted`
- `posted_to_moltbook` → `true`
- `posted_at` → ISO timestamp
- `post_uuid` → the UUID returned by Moltbook's `POST /posts` response

**Round-trip rule:** the publisher rewrites the file with the updated frontmatter, preserving the body byte-for-byte. Uses a line-based parser that locates the `---` markers and rewrites only the frontmatter block, never touching the body.

**Cross-post caveat:** if `submolt_targets` has multiple submolts and the first post succeeds but the second hits a rate limit, the frontmatter is updated with the FIRST post's UUID and a new field `partial_cross_post: true` is added with a list of unposted targets. The operator can re-run later.

### D. Moltbook client (`scripts/moltbook_client.py`)

Thin Python wrapper around the Moltbook REST API. Keeps all network code in one file for auditing and mockability.

```python
# scripts/moltbook_client.py
from __future__ import annotations
import httpx
from dataclasses import dataclass
from typing import Any

BASE_URL = "https://www.moltbook.com"

@dataclass(frozen=True)
class MoltbookPost:
    uuid: str
    url: str
    submolt: str
    created_at: str

@dataclass(frozen=True)
class RateLimitHeaders:
    limit: int
    remaining: int
    reset_epoch: int

class MoltbookClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL):
        if not api_key:
            raise ValueError("MOLTBOOK_API_KEY is required")
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )

    def get_agent_status(self) -> dict:
        """GET /agents/me — returns the authenticated agent's profile."""
        resp = self._client.get("/api/v1/agents/me")
        resp.raise_for_status()
        return resp.json()

    def create_post(
        self,
        *,
        title: str,
        body: str,
        submolt: str,
    ) -> tuple[MoltbookPost, RateLimitHeaders]:
        """POST /posts — creates a new post in the given submolt.

        Returns (post, rate_limit_headers). Raises httpx.HTTPError on failure.
        """
        resp = self._client.post(
            "/api/v1/posts",
            json={"title": title, "body": body, "submolt": submolt, "type": "text"},
        )
        if resp.status_code == 429:
            raise RateLimitError(
                retry_after=int(resp.headers.get("X-RateLimit-Reset", 0)),
                reason=resp.json().get("error", "rate limited"),
            )
        resp.raise_for_status()
        data = resp.json()
        rate = RateLimitHeaders(
            limit=int(resp.headers.get("X-RateLimit-Limit", 0)),
            remaining=int(resp.headers.get("X-RateLimit-Remaining", 0)),
            reset_epoch=int(resp.headers.get("X-RateLimit-Reset", 0)),
        )
        return MoltbookPost(
            uuid=data["uuid"],
            url=f"{BASE_URL}/post/{data['uuid']}",
            submolt=submolt,
            created_at=data["created_at"],
        ), rate

    def search_submolts(self, query: str, limit: int = 25) -> list[dict]:
        """GET /search?q=... — used by register-wizard to help find relevant submolts."""
        resp = self._client.get("/api/v1/search", params={"q": query, "limit": limit})
        resp.raise_for_status()
        return resp.json().get("submolts", [])

class RateLimitError(Exception):
    def __init__(self, retry_after: int, reason: str):
        self.retry_after = retry_after
        self.reason = reason
        super().__init__(f"Moltbook rate limit hit: {reason} (retry after {retry_after}s)")
```

**Key decisions:**
- `httpx` over `requests` — async-capable later if needed, better timeouts
- Timeout hardcoded to 10s total / 5s connect — prevent hanging on Moltbook availability issues
- `raise_for_status()` on non-429 errors — fail loudly, operator sees the error
- Rate limit state returned alongside post data — caller decides how to persist

### E. Local state persistence (`scripts/.moltbook-state.json`)

```json
{
  "schema_version": "1.0",
  "last_post": {
    "uuid": "d45e46d1-4cf6-4ced-82b4-e41db2033ca5",
    "submolt": "m/designsystems",
    "title": "Building a DESIGN.md → Tailwind token pipeline in a day",
    "posted_at": "2026-04-15T14:32:11+00:00",
    "source_file": "project-feed/2026-04-10-design-md-token-pipeline.md"
  },
  "rate_limit": {
    "limit": 2,
    "remaining": 1,
    "reset_epoch": 1718476331,
    "updated_at": "2026-04-15T14:32:11+00:00"
  },
  "agent": {
    "name": "agent-memory-unified",
    "profile_url": "https://www.moltbook.com/u/agent-memory-unified"
  }
}
```

**Gitignored.** Never committed. Recreated by the publisher on first run after a fresh clone.

**Rate limit behavior:** before any `publish` call, the publisher reads the state file. If `rate_limit.reset_epoch > now` AND `rate_limit.remaining == 0`, it refuses with:

```
Rate limit exceeded. Next post allowed at 2026-04-15 15:02:11 UTC (27 minutes from now).
Use --force-post to override (not recommended).
```

### F. Secret scanning (`scripts/test_secret_scan.py` + inline check)

Before any post body is sent over the network, it's scanned for forbidden substrings:

```python
FORBIDDEN_PATTERNS = [
    # API keys and tokens
    (r"STA_[A-Z_]+=", "STA_ env var assignment"),
    (r"B64_(COLDKEY|HOTKEY)", "Bittensor wallet reconstruction var"),
    (r"(?i)api[_-]?key\s*[:=]\s*['\"][a-zA-Z0-9_-]{10,}['\"]", "api key literal"),
    (r"(?i)bearer\s+[a-zA-Z0-9_-]{20,}", "Bearer token"),
    (r"(?i)(password|passwd)\s*[:=]", "password assignment"),
    (r"(?i)secret\s*[:=]\s*['\"]", "secret assignment"),
    # Wallets
    (r"5[a-zA-Z0-9]{47}", "Substrate/Bittensor address (might be OK, warn)"),
    (r"0x[a-fA-F0-9]{40}\b", "Ethereum address (might be OK, warn)"),
    # Private keys
    (r"-----BEGIN .*PRIVATE KEY-----", "PEM private key"),
    (r"ssh-(rsa|ed25519|ecdsa)\s+AAAA", "SSH public key (warn)"),
    # Environment URLs that shouldn't be public
    (r"postgres://[^@\s]+:[^@\s]+@", "Postgres connection string with credentials"),
    (r"redis://[^@\s]+:[^@\s]+@", "Redis connection string with credentials"),
]
```

Scan target: the **formatted post body** (after frontmatter extraction, after summary prepending, after source links appending — exactly what would go on the wire).

**Behavior:**
- Any match → refuse to post, print the pattern name and the matched line, exit non-zero
- `--force-post` overrides the scan (logged loudly, operator is on the hook)
- The scan also runs in `preview` mode so you see violations before trying to publish

### G. Post body formatting

```python
def format_post_body(frontmatter: dict, markdown_body: str) -> str:
    """Build the post body as it'll appear on Moltbook.

    Pattern:
    - Opening paragraph: the `summary` field (ensures context if the body starts abruptly)
    - The markdown body from the file
    - Separator
    - Sources section built from frontmatter['source_links']
    - Footer: attribution line ("Posted from project-feed/... by @<handle>")
    """
    parts = []
    summary = frontmatter.get("summary", "").strip()
    if summary and not markdown_body.strip().startswith(summary):
        parts.append(f"_{summary}_\n")
    parts.append(markdown_body.strip())
    source_links = frontmatter.get("source_links", [])
    if source_links:
        parts.append("\n\n---\n\n**Sources:**")
        for link in source_links:
            link_type = link.get("type", "link")
            url = link.get("url", "")
            if link_type == "commits":
                parts.append(f"- Commits: `{link.get('range', url)}`")
            else:
                parts.append(f"- {link_type.capitalize()}: `{url}`")
    handle = get_agent_handle_from_state()  # reads the state file
    parts.append(f"\n\n_Posted via project-feed by @{handle}_")
    return "\n".join(parts)
```

**Length check:** if the formatted body exceeds a reasonable limit (say, 10,000 chars), warn the operator. Moltbook's actual limit is undocumented; 10k is a conservative starting point.

### H. Register wizard (`register-wizard` subcommand)

A non-automated walkthrough that prints instructions for the human registration steps (because Twitter verification can't be automated):

```
$ python scripts/publish-to-moltbook.py register-wizard

Moltbook agent registration wizard
===================================

This script cannot automate the full registration — Moltbook requires
a Twitter post from your account to verify agent ownership. These
instructions walk you through the manual steps.

Step 1: Open https://www.moltbook.com/ in your browser
  [Press Enter when ready]

Step 2: Read https://www.moltbook.com/skill.md for the canonical onboarding flow
  [Press Enter when ready]

Step 3: Register an agent at https://www.moltbook.com/developers
  Suggested name: agent-memory-unified
  Suggested description: Bittensor Subnet 8 validator + multi-agent trading engine. Posts technical milestones.
  [Press Enter when done]

Step 4: Copy the API key from the registration response.
  WARNING: the key is shown once. Copy it before closing the tab.
  [Press Enter when you have the key saved somewhere safe]

Step 5: Paste the API key here (input will NOT echo):
  MOLTBOOK_API_KEY: [input]
  [Saved to trading/.env as MOLTBOOK_API_KEY=...]
  [Verified .env is in .gitignore ✓]

Step 6: Follow the claim URL shown on the Moltbook page
  Email verification: check your inbox, click the link
  [Press Enter when email verified]

Step 7: Twitter verification
  Moltbook will give you a specific tweet text with a verification code.
  Post it from the X account that owns the email you registered.
  [Press Enter when tweet posted]

Step 8: Return to Moltbook and confirm the claim
  [Press Enter when claim confirmed]

Step 9: Verifying registration by calling GET /agents/me...
  [Runs `python scripts/publish-to-moltbook.py status`]
  ✓ Registration complete. Agent: @agent-memory-unified
  ✓ State file written to scripts/.moltbook-state.json
```

The wizard writes `MOLTBOOK_API_KEY` to `trading/.env` (appending, not overwriting) and verifies `.env` is gitignored before exiting. It is **never** automated — the operator has to walk through it once.

## 4. Tech Stack

- **Language:** Python 3.13 (matches the rest of the project)
- **HTTP client:** `httpx` (already in `trading/pyproject.toml`; add to `scripts/requirements.txt` if not)
- **YAML parser:** `pyyaml` (already in the project)
- **CLI framework:** `argparse` (stdlib, no dep) OR `click` if the publisher grows — start with `argparse`
- **Testing:** `pytest` + `httpx.MockTransport` for HTTP mocking (avoids actual Moltbook network calls in tests)

## 5. Dependencies

### Hard dependencies (must exist before the publisher can run)

- **`project-feed/` directory with at least one `status: ready` entry** — otherwise nothing to publish
- **`MOLTBOOK_API_KEY` environment variable** — either in `trading/.env` or exported in the shell
- **Moltbook agent registered + Twitter verified** — the human-in-the-loop step from the register-wizard. This is **the ONE thing in this entire Moltbook integration that can never be automated.**

### Soft dependencies (nice but not required)

- **`public_surface` track's `/engine/v1/public/milestones` endpoint** — the publisher writes `status: posted` back into `project-feed/*.md`, which the public endpoint reads. They're designed to work together but the publisher is fully functional without the endpoint existing.
- **`defensive_perimeter` track's rate limiting** — the publisher is the *caller* of Moltbook's API, so our own rate limiting doesn't affect it directly. But if the publisher is ever wrapped in a cron job (post-v1), our rate limiting would apply to the cron's callers.

## 6. Security requirements

1. **`MOLTBOOK_API_KEY` is never logged, printed, or committed.** The secret scan applies to the publisher's own stdout/stderr — any diagnostic output that might contain the key is redacted before printing.
2. **The `.env` file is gitignored.** Verified by a pre-commit check in the register-wizard.
3. **State file (`scripts/.moltbook-state.json`) is gitignored.** It contains post UUIDs and timestamps but not the API key; still not committed to keep the repo clean.
4. **HTTPS only.** `BASE_URL` hardcoded to `https://www.moltbook.com`; the client refuses HTTP.
5. **No credential reuse.** The Moltbook API key is only used against `https://www.moltbook.com`. If a future follow-up adds other Moltbook-compatible endpoints, they must require a separate config entry.
6. **Error messages sanitized.** Responses from Moltbook (including error bodies) are scanned for secrets before being logged.
7. **Secret scan is opt-out-only.** `--force-post` exists but is logged at WARNING level with the pattern names that would have been caught.
8. **Moltbook breach awareness.** Per `reference_moltbook.md`, Moltbook has had two breaches (Jan + Feb 2026) exposing API tokens. The publisher assumes the API key may be rotated without warning — all failures include "key may have been rotated; re-register if needed" in the error message.

## 7. Quality gates

- [ ] **Unit tests for frontmatter parsing** — valid, malformed, missing fields
- [ ] **Unit tests for post body formatting** — summary prepending, source links section, footer
- [ ] **Unit tests for the secret scanner** — matches all `FORBIDDEN_PATTERNS`, allows clean text
- [ ] **Unit tests for rate limit state** — loads, saves, refuses when exhausted, resumes after reset
- [ ] **Unit tests for frontmatter round-trip** — body bytes preserved, only frontmatter updates
- [ ] **Integration test with mocked Moltbook** — full publish flow against `httpx.MockTransport`, verifies the correct URL, headers, body
- [ ] **CLI smoke test** — `python scripts/publish-to-moltbook.py list` returns a valid listing even with no `MOLTBOOK_API_KEY` set
- [ ] **Dry-run test** — `python scripts/publish-to-moltbook.py publish <file>` without `--yes` prints the preview, asks for confirmation, and exits cleanly on N
- [ ] **Secret-leak test** — the `secret-leak.md` fixture triggers the scanner and aborts with non-zero exit code
- [ ] **`already-posted.md` fixture test** — publisher refuses to re-post a file with `posted_to_moltbook: true`

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| API key leaks into git history | `.env` gitignored + register-wizard verifies + secret scanner runs on the publisher's own output |
| Rate limit hit mid-run leaves partial state | Write state file after every network call; operator can re-run and see the last successful post |
| Cross-post partial failure (submolt #1 posts, submolt #2 rate-limits) | `partial_cross_post: true` in frontmatter + list of unposted targets; re-run picks up the rest |
| Moltbook API shape changes | Thin client isolates all HTTP calls to one file; contract tests against `httpx.MockTransport` catch drift; human review of any API shape change is required |
| Operator runs `--force-post` with secrets in body | WARNING log, but operator is ultimately on the hook. The secret scanner plus the preview-before-publish gate are the defense; if they're bypassed, the operator accepted the risk |
| Moltbook has a bug and accepts malformed posts silently | Integration tests verify the response body matches expected shape; if Moltbook ever returns a 200 without a UUID, the publisher refuses to update the frontmatter |
| Twitter verification tweet gets deleted | The register-wizard notes this; operator re-runs `register-wizard` if their agent gets de-verified. The publisher's `status` command surfaces the claim status from `GET /agents/me` |
| `httpx` pin drifts from `trading/pyproject.toml` | Publisher reads httpx from the same virtualenv as the trading engine; no separate pin |

## 9. Out of scope / future work

- **Automated posting** (cron, CI trigger, webhook) — post-v1 after manual runs build confidence
- **Comment / reply reading** — no bidirectional sync; Moltbook has no webhooks anyway
- **Multi-agent identity support** — one `MOLTBOOK_API_KEY` at a time
- **Image / media upload** — Moltbook API is text + link only
- **Submolt auto-discovery** — the `register-wizard` has a `search_submolts` helper, but the publisher's `submolt_targets` is currently hand-authored in frontmatter
- **Post editing** — the Moltbook API has `PATCH /posts/:id`, but we're treating posts as immutable for v1 (follow-up post instead of edit)
- **Post deletion** — `DELETE /posts/:id` exists but isn't wired; manual via curl if needed
- **Upvote / follow management** — not part of the publisher's scope
- **Rate limit backoff with retry** — v1 refuses; automatic retry is a follow-up
- **Prometheus metrics for publish success/failure** — deferred to `abuse_response` track

## 10. References

- Moltbook reference: `reference_moltbook.md` (API shape, rate limits, security history, onboarding flow)
- Project-feed convention: `reference_project_feed_convention.md` (frontmatter schema, status field lifecycle)
- Audit: `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- Companion: `conductor/tracks/moltbook_publisher/audit-cross-ref.md`
- Sibling tracks: `public_surface` (consumes `status: posted` files via `/milestones` endpoint), `defensive_perimeter` (our own API rate limiting; unrelated to Moltbook's rate limiting on us as a caller)
- Moltbook API skill file: `https://www.moltbook.com/skill.md`
- Moltbook API GitHub: `https://github.com/moltbook/api`
