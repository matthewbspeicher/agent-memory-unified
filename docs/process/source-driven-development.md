# Source-Driven Development

> Adapted from [addyosmani/agent-skills/skills/source-driven-development](https://github.com/addyosmani/agent-skills/blob/main/skills/source-driven-development/SKILL.md) (MIT). Examples and cautionary tales tailored to this repository.

## Overview

Every framework-specific code decision must be backed by **official documentation** — not training data, not blog posts, not Stack Overflow. Don't implement from memory: verify, cite, and let the user see your sources. Training data goes stale, APIs get deprecated, best practices evolve.

This skill exists because we've been bitten in this exact repository:

- **Bittensor v10 logger kill** (`feedback_bittensor_v10_logging.md`) — `import bittensor` silently sets every existing logger to `CRITICAL`. Not in the v9 docs we'd internalized; only discovered by reading v10 source.
- **Bittensor v10 API changes** (`feedback_bittensor_v10_api.md`) — `bt.Subtensor` not `bt.subtensor`; `network=` not `chain_endpoint=`. Confidently-wrong code from training data merged before someone read the actual v10 changelog.
- **`ExchangeClient` constructor signature** (`feedback_exchangeclient_api.md`) — uses `primary=`, not `exchange_id=`. Four call sites built on the wrong signature on 2026-04-09.

In each case, **a single docs fetch would have prevented hours of rework**. This document is the standing rule that the fetch happens.

## When to Use

- About to write framework-specific code (Bittensor, IBKR, FastAPI, Pydantic, SQLAlchemy, pgvector, React 19, Vite, TanStack Query, axios, taoshi PTN, etc.)
- Building boilerplate or starter code that will be copied across the project (the wrong pattern multiplies)
- The user explicitly asks for documented, verified, or "correct" implementation
- Implementing features where the framework's recommended approach matters (forms, routing, data fetching, state management, auth, ORM patterns)
- Touching any of the libraries listed in this project's `feedback_*` memory entries — we already know they have version-specific gotchas
- Reviewing or improving code that uses framework-specific patterns
- **Any time** you're about to write framework-specific code from memory

**When NOT to use:**

- Pure logic that works the same across all versions (loops, conditionals, data structures, algorithms)
- Renaming variables, fixing typos, moving files
- Writing tests that exercise our own code without depending on framework version specifics
- The user has explicitly authorized speed over verification ("just patch this real quick")

## The Process

```
DETECT ──→ FETCH ──→ IMPLEMENT ──→ CITE
  │          │           │            │
  ▼          ▼           ▼            ▼
 What       Get the    Follow the   Show your
 stack +    relevant   documented   sources
 version?   docs       patterns
```

### Step 1: Detect Stack and Versions

Read this project's dependency files to identify exact versions:

| File | Owns |
|---|---|
| `trading/pyproject.toml` | Trading engine Python deps (FastAPI, Bittensor, Pydantic, SQLAlchemy, pgvector client, etc.) |
| `taoshi-vanta/requirements.txt` | Taoshi validator deps — **bittensor 9.12.1**, separate venv, do not mix with trading |
| `frontend/package.json` | React 19, Vite, TanStack Query, axios, etc. |
| `frontend/package-lock.json` | Resolved versions |
| `shared/types/package.json` | Shared TypeScript type generation tooling |

State what you found explicitly before writing any code:

```
STACK DETECTED:
- bittensor 10.x (from trading/pyproject.toml — pin says >=10.0.0)
- FastAPI 0.115.x
- Pydantic 2.x
- pgvector via psycopg2 + raw SQL
→ Fetching official docs for the relevant patterns.

NOTE: taoshi-vanta/ uses bittensor 9.12.1 in a SEPARATE venv. Patches there
follow v9 conventions, not v10. Do not cross-import.
```

If versions are missing or ambiguous, **ask the user**. Don't guess — the version determines which patterns are correct, and this project specifically straddles two incompatible bittensor major versions.

### Step 2: Fetch Official Documentation

Fetch the specific documentation page for the feature you're implementing. Not the homepage, not the full docs — the relevant page.

**Tools available in this project, in order of preference:**

| Priority | Tool | When to use |
|---|---|---|
| 1 | `mcp__claude_ai_Context7__query-docs` (Context7 MCP) | Mainstream libraries — React, FastAPI, Pydantic, SQLAlchemy, Tailwind, Vite. Returns current docs scoped to a query. Use Context7 first. |
| 2 | `gh api repos/<owner>/<repo>/contents/<path>` | GitHub-hosted docs and source — Bittensor SDK, Taoshi PTN, Subnet 8 docs, our own CLAUDE.md. Faster than WebFetch for github.com. |
| 3 | `WebFetch` | Anything else — official documentation sites not indexed by Context7, blog posts that document migration paths, vendor changelogs |
| 4 | Reading source directly via `Read` | When fetching docs is impossible and the source is in our worktree (e.g. `taoshi-vanta/`) |

**Source hierarchy (in order of authority):**

| Priority | Source type | Examples for this project |
|---|---|---|
| 1 | Official documentation | docs.bittensor.com, fastapi.tiangolo.com, react.dev, docs.pydantic.dev, www.postgresql.org/docs |
| 2 | Official source code in the version we're using | `taoshi-vanta/`, `gh api repos/opentensor/bittensor`, `gh api repos/taoshidev/proprietary-trading-network` |
| 3 | Official changelog / migration guide | Bittensor v9→v10 release notes, FastAPI release notes, React 19 upgrade guide |
| 4 | Web standards references | MDN, web.dev — for browser/JS/CSS questions |

**Not authoritative — never cite as primary sources:**

- Stack Overflow answers (even highly upvoted ones)
- Medium / Dev.to / personal blog posts
- AI-generated documentation or summaries (including this document — verify the addyosmani upstream if in doubt)
- Your own training data (this is the whole point — verify it)
- Old GitHub issues whose resolution was never merged
- README files of forks or unofficial mirrors

**Be precise with what you fetch:**

```
BAD:  Fetch the FastAPI homepage
GOOD: Fetch fastapi.tiangolo.com/advanced/events/#lifespan

BAD:  gh api repos/opentensor/bittensor
GOOD: gh api repos/opentensor/bittensor/contents/bittensor/core/subtensor.py

BAD:  Search "react 19 forms"
GOOD: Fetch react.dev/reference/react/useActionState
```

After fetching, extract the key patterns and **note any deprecation warnings or migration guidance**. If you see a "Deprecated since X.Y" banner, that's load-bearing.

When official sources conflict with each other (e.g. a migration guide contradicts the API reference), surface the discrepancy to the user and verify which pattern actually works against the detected version.

### Step 3: Implement Following Documented Patterns

Write code that matches what the documentation shows:

- Use the API signatures **from the docs**, not from memory
- If the docs show a new way to do something, use the new way
- If the docs deprecate a pattern, don't use the deprecated version
- If the docs don't cover something, **flag it as unverified**

**When docs conflict with existing project code:**

```
CONFLICT DETECTED:
The existing codebase uses bt.subtensor() (lowercase) in trading/integrations/bittensor/adapter.py:34
but the v10 docs and source require bt.Subtensor() (capital S).
(Source: github.com/opentensor/bittensor v10.0.0 — bittensor/__init__.py exports `Subtensor`)

The existing usage is from a v9-era pattern that v10 broke.

Options:
A) Update adapter.py to use bt.Subtensor (correct for our pinned v10)
B) Leave adapter.py as-is (will fail at runtime)
→ I recommend (A) — option (B) is broken code. Confirming before I edit?
```

Surface the conflict. **Don't silently pick one.** And don't silently update either — ask first if it's outside the scope of the current task.

**When docs conflict with this repository's CLAUDE.md or memory:**

Memory and CLAUDE.md document hard-won lessons. If the docs say one thing and our memory says "we tried that, it kills loggers" — **trust the memory and verify**. The memory is a record of what actually happened in our running system.

### Step 4: Cite Your Sources

Every framework-specific pattern gets a citation. The user must be able to verify every decision.

**In code comments** (sparingly — only for non-obvious decisions):

```python
# Bittensor v10: Subtensor class is the connection (capital S, not v9's bt.subtensor)
# Source: https://github.com/opentensor/bittensor/blob/v10.0.0/bittensor/__init__.py
subtensor = bt.Subtensor(network="finney")
```

```typescript
// React 19 form action with built-in pending state
// Source: https://react.dev/reference/react/useActionState#usage
const [state, formAction, isPending] = useActionState(submitOrder, initialState);
```

**In conversation** (always for non-obvious framework-specific decisions):

> I'm using `useActionState` instead of manual `useState` for the form submission state. React 19 added this hook specifically to replace the manual `isPending`/`setIsPending` pattern.
>
> Source: https://react.dev/blog/2024/12/05/react-19#actions
> Quote: *"useTransition now supports async functions [...] to handle pending states automatically"*

**Citation rules:**

- Full URLs, not shortened
- Prefer deep links with anchors where possible (`/useActionState#usage` over `/useActionState`) — anchors survive doc restructuring better
- Quote the relevant passage when it supports a non-obvious decision
- Include browser/runtime support data when recommending platform features
- For Bittensor specifically: link to the **tagged release** (`/blob/v10.0.0/...`) not `main`, because main moves
- If you cannot find documentation for a pattern, say so explicitly:

> **UNVERIFIED:** I could not find official Bittensor documentation for the `Subtensor.set_weights()` retry behavior. The implementation in `trading/integrations/bittensor/weight_setter.py:147` is based on training data and a reading of `bittensor/core/subtensor.py:set_weights` source. Verify against a real call before relying on the retry semantics.

**Honesty about what you couldn't verify is more valuable than false confidence.** A flagged unknown is a checkable claim; a confidently wrong claim is a bug waiting to ship.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I'm confident about this Bittensor API" | Confidence is exactly what got us the v10 logger kill, the `bt.subtensor` typo, and the `ExchangeClient(exchange_id=)` mistake. Confidence is not evidence. Verify. |
| "Fetching docs wastes tokens" | Hallucinating an API costs hours of debugging. One Context7 query or one `gh api` call costs seconds. The math is not close. |
| "The docs won't cover this edge case" | Then read the source via `gh api` or `Read taoshi-vanta/...`. If the source doesn't cover it either, flag it as **UNVERIFIED** in your output. |
| "I'll just mention it might be outdated" | A disclaimer doesn't help. Either verify and cite, or clearly flag as unverified with an action item. Hedging is the worst option. |
| "This is a simple task, no need to check" | Simple tasks become templates. The wrong pattern in one place becomes the wrong pattern in ten places. |
| "The CLAUDE.md already covers this" | CLAUDE.md is a starting point, not a substitute for current docs. CLAUDE.md will drift. Always cross-check against the live source for the version pinned in `pyproject.toml` / `package.json`. |
| "I read the README, that's enough" | READMEs are marketing. API references are documentation. They are not interchangeable. |
| "I already cited this URL earlier in the session" | Re-link it for the current decision. Future-you reading the conversation log shouldn't have to scroll. |

## Red Flags

Stop and verify if you catch yourself doing any of these:

- Writing Bittensor code without checking the version pin in `trading/pyproject.toml` (or `taoshi-vanta/requirements.txt` if you're working in there)
- Writing FastAPI lifespan code from memory without checking the version
- Using "I believe" or "I think" about an API instead of citing the source
- Implementing a pattern without knowing which **major version** it applies to
- Citing Stack Overflow, Medium posts, or blog posts as primary sources
- Using deprecated APIs because they appear in training data
- Not reading dependency files before implementing
- Delivering code without source citations for framework-specific decisions
- Fetching an entire docs site when only one page is relevant
- Reaching for `WebFetch` when Context7 or `gh api` would be faster and more authoritative
- Writing a `try/except` for an exception you're not sure the library actually raises
- Naming a function the way you remember the framework documenting it, without checking

## Verification Checklist

Before declaring a framework-specific implementation done, confirm all of these:

- [ ] Framework and library versions were identified from the dependency file (and noted in the conversation)
- [ ] If working near `taoshi-vanta/`, the v9 vs v10 bittensor distinction was confirmed
- [ ] Official documentation or source was fetched for every framework-specific pattern used
- [ ] All sources are official documentation, official source code at the correct tag, or official changelogs — not blog posts or training data
- [ ] Code follows the patterns shown in the current version's documentation
- [ ] Non-trivial decisions include source citations with full URLs in the conversation
- [ ] Deep links / anchors used where the doc page supports them
- [ ] No deprecated APIs are used (checked against the version's migration guide)
- [ ] Conflicts between docs and existing code were surfaced to the user before editing
- [ ] Anything that could not be verified is explicitly flagged as **UNVERIFIED** in the output
- [ ] If `import bittensor` happens anywhere in the new code path, the logger restoration is in place (CLAUDE.md "Working Boundaries" → Always do)

---

## Project-specific source pointers

A starter set of authoritative sources for the libraries this project uses heavily:

| Library | Where to look |
|---|---|
| **Bittensor v10** (trading engine) | `gh api repos/opentensor/bittensor/contents/bittensor/__init__.py?ref=v10.0.0` and tagged release notes; docs.bittensor.com (cross-check version) |
| **Bittensor v9.12.1** (taoshi-vanta) | `Read taoshi-vanta/...` directly — it's mounted into our worktree |
| **Taoshi PTN / Subnet 8** | `gh api repos/taoshidev/proprietary-trading-network/...` |
| **FastAPI** | fastapi.tiangolo.com — version listed in `trading/pyproject.toml` |
| **Pydantic v2** | docs.pydantic.dev/latest — note v1 vs v2 differences are massive |
| **SQLAlchemy 2.x** | docs.sqlalchemy.org/en/20/ — 2.x style is `Mapped[...]`, not 1.x classical |
| **pgvector** | `gh api repos/pgvector/pgvector` for the SQL operators; psycopg docs for the Python binding |
| **React 19** | react.dev — verify it's the v19 docs; v18 docs are still online |
| **Vite** | vitejs.dev — version in `frontend/package.json` |
| **TanStack Query** | tanstack.com/query/latest — v5 API differs significantly from v4 |
| **IBKR ib_insync / ib_async** | `gh api repos/ib-api-reloaded/ib_async` — `ib_insync` is unmaintained |

Add to this table when you discover a new authoritative source for one of our dependencies.

---

*Adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills/blob/main/skills/source-driven-development/SKILL.md) under MIT license. Process structure preserved; examples and cautionary tales drawn from this repository's incident history.*
