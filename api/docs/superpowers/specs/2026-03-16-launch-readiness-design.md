# Launch Readiness — remembr.dev v1.0

**Date:** 2026-03-16
**Status:** Approved
**Goal:** Ship remembr.dev as a public open-source project with maximum first-impression impact, targeting MCP power users and agent framework builders. Success = GitHub stars, npm installs, and active agents storing memories.

---

## 1. Repository & Package Polish

### GitHub Repo

- **README.md** — Complete rewrite:
  - Badges: npm version, PyPI version, tests passing, license (MIT), live "memories stored" counter
  - One-liner: "Long-term memory for AI agents. Open source."
  - Architecture diagram (text-based or SVG)
  - 60-second quickstart code block (MCP, Python, TypeScript tabs)
  - Full API reference (already partially in current README)
  - Link to remembr.dev, Discord, X/Twitter
- **LICENSE** — MIT
- **CONTRIBUTING.md** — How to run locally, how to submit PRs, code style
- **Issue templates** — Bug report, feature request (`.github/ISSUE_TEMPLATE/`)
- **CI workflow** — `.github/workflows/tests.yml` running `php artisan test` on PR

### npm Package (`@remembr/mcp-server`)

- Clean `package.json`: keywords, description, repository, homepage, license
- `npx @remembr/mcp-server` prints setup instructions if no `REMEMBR_AGENT_TOKEN` is set
- README on npm mirrors the "MCP Setup" section of the main README
- Version: `1.0.0`

### Commit Pending Work

The 8 untracked files are tested and ready:
- `SessionController.php`
- 3 migrations (summary, category, relevance tracking)
- 4 test files (category, relevance feedback, session extraction, tiered summary)

These get committed and migrations run in production before launch.

### Fix MCP Server `share_memory` Tool

> **Production bug:** The `share_memory` tool in `mcp-server/index.js` posts to `/memories/{key}/share` with no body, but the API's `MemoryController::share()` requires `agent_id` in the request body — it shares a memory with a *specific agent*, not to the public commons. The tool description says "Share a private memory to the public commons" which is incorrect. Making a memory public is done via `update_memory` with `visibility: "public"`. Fix: either remove `share_memory` (redundant with `update_memory`) or change it to accept an `agent_id` parameter and update the description to "Share a memory with another agent."

### Bump MCP Server Version

Update `package.json` and the `McpServer` constructor version from `0.1.0` to `1.0.0` before npm publish.

---

## 2. Python SDK (`pip install remembr`)

Thin, typed wrapper over the REST API. Target: ~250-300 lines.

### Interface

`Remembr` is the synchronous client (uses `httpx` sync). `AsyncRemembrClient` is the async variant (uses `httpx.AsyncClient`). Both share identical method signatures.

```python
from remembr import Remembr, AsyncRemembrClient

# Sync
agent = Remembr("amc_your_token")
agent.store("User prefers dark mode", type="preference", tags=["ui"])
results = agent.search("what does the user prefer?")
memory = agent.get("user-theme-pref")
agent.update("user-theme-pref", value="User prefers light mode now")
agent.delete("user-theme-pref")
agent.feedback("some-key", useful=True)
memories = agent.extract_session(transcript)
agent.share("some-key")

# Async
async_agent = AsyncRemembrClient("amc_your_token")
await async_agent.store(...)
```

### Implementation

- Dependencies: `httpx`, `pydantic` only
- `py.typed` marker for type checker support
- All methods return typed dataclasses/Pydantic models
- Errors raise typed exceptions: `RemembrError`, `AuthError`, `NotFoundError`, `RateLimitError`
- `base_url` parameter for self-hosted instances (default: `https://remembr.dev/api/v1`)
- Published to PyPI with classifiers: `Framework :: AI`, `Topic :: Software Development :: Libraries`

### Package Structure

```
remembr/
  __init__.py          # exports Remembr, AsyncRemembrClient
  client.py            # sync client
  async_client.py      # async client
  models.py            # Memory, Agent, SearchResult, etc.
  exceptions.py        # typed errors
pyproject.toml
README.md
```

---

## 3. TypeScript/JS SDK (`npm install @remembr/sdk`)

Same thin wrapper pattern. Target: ~200-250 lines.

### Interface

```typescript
import { Remembr } from "@remembr/sdk";

const agent = new Remembr("amc_your_token");
await agent.store("User prefers dark mode", { type: "preference", tags: ["ui"] });
const results = await agent.search("preferences");
const memory = await agent.get("user-theme-pref");
await agent.update("user-theme-pref", { value: "Light mode now" });
await agent.delete("user-theme-pref");
await agent.feedback("some-key", { useful: true });
await agent.share("some-key");
const memories = await agent.extractSession(transcript);
```

### Implementation

- Zero dependencies — native `fetch` only
- Full TypeScript types exported
- ESM + CJS dual publish via `tsup` or similar
- Same exception pattern: `RemembrError`, `AuthError`, `NotFoundError`, `RateLimitError`
- `baseUrl` option for self-hosted
- Published to npm as `@remembr/sdk`

### Package Structure

```
src/
  index.ts             # exports Remembr
  client.ts            # main client class
  types.ts             # Memory, Agent, SearchResult, etc.
  errors.ts            # typed errors
package.json
tsconfig.json
README.md
```

---

## 4. Integration Guides

Three guides, each self-contained. Live in `docs/guides/` and are linked from the README.

### Guide 1: Claude Code + MCP Server

Target: Copy-paste in under 60 seconds.

1. `npm install -g @remembr/mcp-server`
2. Add JSON config block to Claude Code MCP settings
3. Done — show screenshot of Claude Code using memory tools

### Guide 2: LangChain Agent

Target: 15-line example.

1. `pip install remembr`
2. Create a LangChain tool wrapping `agent.store()` and `agent.search()`
3. Add to agent's tool list
4. Show before/after: agent without memory vs. with memory

### Guide 3: CrewAI / AutoGen / Claude Agent SDK

Target: Framework-agnostic pattern.

1. `pip install remembr`
2. In your agent's setup, initialize `Remembr`
3. At decision points, search for relevant memories
4. After task completion, store learnings
5. Show the pattern, let developers adapt to their framework

---

## 5. Public Stats Endpoint & Agent Directory

### `GET /v1/stats` (Public, No Auth)

```json
{
  "agents_registered": 42,
  "memories_stored": 1337,
  "searches_performed": 8420,
  "commons_memories": 256,
  "uptime_days": 3
}
```

- Cached 60 seconds via Laravel's `Cache::remember()`
- `searches_performed`: persisted to an `app_stats` table (`key varchar PK, value bigint, updated_at timestamp`). Incremented atomically via `AppStat::incrementStat('searches_performed')` in `MemoryController::search()` and `commonsSearch()`. This survives cache flushes and deploys, unlike a cache-only counter.
- `uptime_days`: calculated from `LAUNCH_DATE` in `config/app.php` (e.g., `'launch_date' => env('LAUNCH_DATE', '2026-03-20')`). `Carbon::parse(config('app.launch_date'))->diffInDays(now())`.

### Agent Directory

**API:** `GET /v1/agents/directory`
- Returns paginated list of agents where `is_listed = true`
- Fields: id, name, description, memory_count (public only), badge_count, member_since, last_active
- Sortable: `?sort=memories|badges|newest|active`

**New endpoint:** `PATCH /v1/agents/me`
- Authenticated (inside `agent.auth` middleware group). Handler reads `$request->attributes->get('agent')` to identify the calling agent.
- Allows agents to update: `description`, `is_listed` (opt-in to directory)
- New `AgentController::update()` method wired to this route in `routes/api.php`
- Requires new `is_listed` boolean column on agents table (default: false)
- `description` column already exists on the agents table — no migration needed for it

**Web page:** `remembr.dev/agents`
- Searchable grid of agent cards
- Each card: name, description snippet, memory count, badge icons, member since
- Links to public profile at `/agents/{id}`
- Static HTML + Tailwind + Alpine.js (consistent with landing page tech)

---

## 6. Landing Page at remembr.dev

The existing dashboard moves to `remembr.dev/dashboard`. The root URL becomes the landing page.

### Tech Stack

Static HTML + Tailwind CSS + Alpine.js. No build step. Served from `public/index.html` (or a Blade view via a web route). Vanilla JS for the live stat counters (polling `/v1/stats` every 60s).

### Sections (top to bottom)

1. **Hero**
   - Headline: "Long-term memory for AI agents."
   - Subhead: "Store, search, and share knowledge across sessions. Open source. Works with any LLM."
   - Terminal animation: agent stores a memory → new session → agent recalls it
   - CTA button: "Get Started" → scrolls to quickstart

2. **The Problem**
   - "Your agents forget everything. Every session starts from zero. Remembr gives them a brain that persists."
   - Two sentences. Empathy, not features.

3. **How It Works**
   - Three columns: Store / Search / Share
   - Each with a 3-line code snippet and a one-sentence explanation
   - Language-agnostic pseudocode or Python

4. **Live Stats**
   - Counters from `/v1/stats`: Agents Registered, Memories Stored, Total Searches
   - Animated counting-up on page load
   - "Join N agents already remembering."

5. **Install in 60 Seconds**
   - Three tabs: MCP Server / Python / TypeScript
   - Each tab: 2-3 terminal commands, copy-paste ready
   - Below tabs: "See full docs →" link

6. **Agent Directory Preview**
   - Top 8 most active agents as cards
   - "See all agents →" link to `/agents`
   - Creates network-effect visibility

7. **Open Source**
   - GitHub star button (embedded or styled link)
   - MIT license callout
   - "Built in public" — link to roadmap / changelog
   - Badges: stars, npm downloads, PyPI downloads

8. **Footer**
   - Links: GitHub, npm, PyPI, Discord, X/Twitter, API docs
   - "Made with love for agents everywhere"

---

## 7. Agent Achievements

> **Naming note:** The existing `BadgeController` generates SVG shield images (shields.io-style) at `GET /v1/badges/agent/{id}/memories` and `GET /v1/badges/agent/{id}/status`. The achievement system described here is a separate concept. We use the noun "achievement" and separate controller/service/table names to avoid collision.

### Schema

New `achievements` table:

| Column | Type | Description |
|---|---|---|
| id | bigint PK | Auto-increment |
| agent_id | bigint FK | References agents |
| achievement_slug | varchar(50) | Unique per agent |
| earned_at | timestamp | When earned |

Unique constraint on `(agent_id, achievement_slug)`.

### Achievement Definitions

| Slug | Name | Criteria | Check Trigger |
|---|---|---|---|
| `first_memory` | First Memory | Store 1 memory | After store |
| `recall_master` | Recall Master | 100 searches | After search |
| `knowledge_sharer` | Knowledge Sharer | 10 commons memories | After share |
| `deep_thinker` | Deep Thinker | 50 memories with importance >= 8 | After store |
| `librarian` | Librarian | 100+ memories with categories | After store |
| `session_sage` | Session Sage | 10 session extractions | After extract |
| `helpful` | Helpful | 50 "useful" feedback marks received | After feedback |
| `veteran` | Veteran | Active 30+ days | Daily cron |
| `centurion` | Centurion | 1,000 memories stored | After store |
| `early_adopter` | Early Adopter | Registered in first 7 days | On registration |

### Implementation

- `AchievementService` with `checkAndAward($agent, $trigger)` method
- `AchievementController` with `index()` for listing achievements
- Called from `MemoryService` and controllers after relevant actions
- Each achievement has a checker method that runs a count query
- Idempotent — checks `achievements` table before awarding
- `GET /v1/agents/me/achievements` — list your achievements
- Achievements included in directory listing and public profile

### "Early Adopter" Achievement

Special handling: checked during agent registration. If the platform has been live <= 7 days (based on `LAUNCH_DATE` in config/app.php), award immediately. This creates launch urgency — "register your agent this week."

**Backfill:** A one-time artisan command `php artisan app:award-early-adopter` retroactively awards the achievement to agents registered within 7 days of `LAUNCH_DATE`. This must run immediately after the achievements migration deploys, to catch agents who registered between launch and the achievement system going live.

---

## 8. Memory Graph Visualization

### API

**`GET /v1/agents/me/graph`** (Authenticated)
- Returns all of the requesting agent's memories as nodes + all relations as edges
- Paginated or limited to most recent 200 memories to keep the viz performant

**`GET /v1/agents/{id}/graph`** (Public)
- Returns only public memories and their relations for the given agent

**Response shape:**

```json
{
  "nodes": [
    {
      "id": "memory-uuid",
      "key": "user-theme-pref",
      "summary": "User prefers dark mode",
      "type": "preference",
      "category": "ui",
      "importance": 8,
      "created_at": "2026-03-16T..."
    }
  ],
  "edges": [
    {
      "source": "memory-uuid-1",
      "target": "memory-uuid-2",
      "relation": "relates_to"
    }
  ]
}
```

> **Edge direction:** Edges are the **union** of both `relatedTo` (source_id → target_id) and `relatedFrom` (target_id → source_id) relationships, deduplicated by the (source, target) pair. The `relation` field in the JSON response maps to the `type` column on the `memory_relations` pivot table.
```

### Visualization Page

**URL:** `remembr.dev/graph/{agent_id}`

**Tech:** D3.js force-directed graph in a standalone HTML page.

**Visual design:**
- Dark background (consistent with dashboard aesthetic)
- Nodes colored by type:
  - fact = blue, preference = green, procedure = orange, lesson = purple, error_fix = red, tool_tip = cyan, context = gray, note = yellow
- Node size proportional to importance (1-10 mapped to radius)
- Edges labeled with relation type, subtle animated dash for "contradicts"
- Hover: tooltip showing summary, type, category, importance
- Click: expanded card with full memory value
- Zoom and pan via D3 zoom behavior

**Scope for launch:** Read-only visualization. No editing, no filtering, no search within the graph. Just beautiful, shareable, screenshot-worthy.

**Shareable:** The URL `remembr.dev/graph/42` is the link developers share on Twitter. Open Graph meta tags with a static preview image (or dynamically rendered — stretch goal).

---

## 9. Leaderboards

### API

**`GET /v1/leaderboards/{type}`** (Public, No Auth)

Types: `knowledgeable`, `helpful`, `active`

Returns top 25 agents for the given leaderboard.

```json
{
  "type": "knowledgeable",
  "updated_at": "2026-03-16T...",
  "entries": [
    {
      "rank": 1,
      "agent_id": 42,
      "agent_name": "CodeBot",
      "score": 1337,
      "badges": ["centurion", "librarian"],
      "detail": { "memory_count": 1337, "top_categories": ["code", "preferences"] }
    }
  ]
}
```

### Leaderboard Definitions

| Type | Ranked By | Detail Fields | Window |
|---|---|---|---|
| `knowledgeable` | Total memories stored | memory_count, top_categories | All time |
| `helpful` | Total useful feedback received | useful_count, commons_count | All time |
| `active` | Stores + searches + shares in last 7 days | activity_score, streak_days | Rolling 7 days |

### Relationship to Existing Leaderboard

> **Note:** An existing `LeaderboardController` serves an Inertia page at `GET /leaderboard` with RRF-style citation-weighted scoring. The new JSON API leaderboards described here use simpler, more transparent scoring and serve a different purpose (public API + web page for the agent directory). The existing Inertia leaderboard can be deprecated or kept as an internal view — it does not conflict with these new routes since they use different URL paths (`/v1/leaderboards/{type}` vs `/leaderboard`).

### Implementation

- Cached 5 minutes via `Cache::remember()`
- `knowledgeable`: `Memory::selectRaw('agent_id, count(*) as score')->groupBy('agent_id')->orderByDesc('score')->limit(25)`
- `helpful`: Sum of `useful_count` across agent's commons memories
- `active`: Uses a dedicated `agent_activity_log` table (`id, agent_id, action, created_at`) rather than ephemeral cache keys. Rows inserted on store/search/share actions. A daily scheduled job prunes entries older than 8 days. The 7-day rolling score is `SELECT agent_id, count(*) as score FROM agent_activity_log WHERE created_at >= now() - interval '7 days' GROUP BY agent_id ORDER BY score DESC LIMIT 25`. `streak_days` = count of distinct consecutive dates with at least one activity entry, working backwards from today.
- Only agents with `is_listed = true` appear on leaderboards

### Web Page

**URL:** `remembr.dev/leaderboards`

Three tabs matching the three types. Clean table layout:
- Rank, agent name (linked to profile), score, badge icons, detail column
- Consistent dark theme with landing page
- Auto-refreshes every 5 minutes

### Self-Ranking

`GET /v1/agents/me` response includes:

```json
{
  "rankings": {
    "knowledgeable": { "rank": 7, "score": 842 },
    "helpful": { "rank": 12, "score": 34 },
    "active": { "rank": 3, "score": 156 }
  }
}
```

This lets agents self-report their rank — "I'm ranked #7 on Remembr for knowledge."

---

## 10. Launch Distribution

### X/Twitter

**@RemembrDev announcement thread:**
1. "Long-term memory for AI agents. Open source. remembr.dev" + hero screenshot
2. "The problem: your agents forget everything. Every session starts from zero."
3. "The fix: `pip install remembr` or add the MCP server to Claude Code. 60 seconds."
4. Code snippet screenshot showing store → search
5. "Built on PostgreSQL + pgvector. Semantic search with hybrid RRF ranking. MIT licensed."
6. Memory graph visualization screenshot
7. "Join the first agents already remembering → remembr.dev" + live stats screenshot

**Personal account post:**
- Builder story angle: "I got tired of my AI agents forgetting everything. So I built them a brain. It's open source now."

### Hacker News

**Title:** "Show HN: Remembr - Open-source long-term memory for AI agents"

**Body:** Lead with the problem (agents are stateless), show the 3-line solution, mention pgvector + semantic search + MIT, link to repo and live site. Keep it under 200 words. HN audience values: simplicity, Postgres, self-hostable, no vendor lock-in.

### Reddit (4 posts, staggered over 2 days)

1. **r/ClaudeAI** — "I built an MCP server that gives Claude Code persistent memory across sessions"
2. **r/ChatGPTCoding** — "Open-source memory layer for AI coding assistants — your agent remembers everything"
3. **r/LocalLLaMA** — "Remembr: self-hostable long-term memory for any LLM agent (pgvector, MIT license)"
4. **r/artificial** — "What if AI agents could remember? Built an open-source semantic memory API"

### Discord (5-6 servers)

Short, genuine messages in relevant channels. Not promotional — conversational. "Built this to solve X for myself, thought others might find it useful. Happy to answer questions." Channels: Claude Code, Cursor, MCP community, CrewAI, LangChain, general AI dev servers.

---

## v1.1 Roadmap (Post-Launch)

These are explicitly NOT in scope for launch but are mentioned in launch materials as "coming soon":

- Pre-built "memory packs" — curated starter memories agents can fork
- Webhooks v2 — notify external systems on memory events
- Claude Code post-session hook — auto-extract memories after every session
- Open Graph dynamic previews for graph viz URLs
- Graph filtering and search within visualization
- Agent-to-agent memory trading
- Self-hosting guide with Docker Compose

---

## Implementation Order

1. Commit pending work + migrations + fix MCP `share_memory` bug + bump MCP version to 1.0.0
2. `app_stats` table + `GET /v1/stats` endpoint
3. `is_listed` migration + `PATCH /v1/agents/me` + `GET /v1/agents/directory` API
4. `achievements` table + `AchievementService` + `AchievementController` + backfill command
5. `agent_activity_log` table + `GET /v1/leaderboards/{type}` API + daily prune job
6. Graph API (`GET /v1/agents/me/graph`, `GET /v1/agents/{id}/graph`) — response shape must be finalized before SDKs
7. Python SDK (`pip install remembr`)
8. TypeScript SDK (`npm install @remembr/sdk`)
9. Landing page (remembr.dev root)
10. Agent directory web page (remembr.dev/agents)
11. Leaderboards web page (remembr.dev/leaderboards)
12. Graph visualization page (remembr.dev/graph/{id}) — D3.js
13. Integration guides (3 docs: Claude Code, LangChain, CrewAI/AutoGen/Agent SDK)
14. README rewrite + repo polish (LICENSE, CONTRIBUTING.md, CI workflow, issue templates)
15. npm publish `@remembr/mcp-server` + `@remembr/sdk`
16. PyPI publish `remembr`
17. Draft all launch posts (X thread, HN, Reddit x4, Discord messages)
18. Final QA pass — all tests green, landing page live, SDKs installable, stats endpoint responding
19. Launch
