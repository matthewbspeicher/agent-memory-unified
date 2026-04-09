# Knowledge System Evolution Plan

## Context

Researched Karpathy's LLM Wiki gist (13,344 stars), two implementation articles, 12+ alternative tools in the space, and cutting-edge academic research on agent memory. The goal: identify what this project's existing `.claude/knowledge/` system already does well, what gaps exist, and what improvements would deliver the highest value.

**Key finding:** This project already implements a mature version of Karpathy's pattern (auto-capture hooks, daily logs, compiled articles, index-guided retrieval, lint). The system is well-architected but currently in "bootstrap" state -- no daily logs, no compiled articles, empty index. The biggest opportunities are: (1) getting the system actually running, (2) adding capabilities the research reveals are high-value.

---

## Research Summary

### What Karpathy Proposes (the gist)
Three-layer architecture: **Raw Sources** (immutable) -> **Wiki** (LLM-maintained markdown) -> **Schema** (compiler spec). Three operations: **Ingest** (source -> 10-15 wiki page touches), **Query** (index-guided retrieval, answers file back as new pages), **Lint** (contradictions, orphans, staleness). Key insight: the LLM handles all the tedious bookkeeping that makes humans abandon wikis.

### What This Project Already Has
- All three layers implemented (daily/ -> articles/ -> AGENTS.md)
- Auto-capture via SessionStart/SessionEnd/PreCompact hooks
- Background flush with knowledge-signal pre-filtering
- Compile, query, and lint scripts with Claude Agent SDK
- State tracking, deduplication, cost tracking
- End-of-day auto-compilation trigger

### What's Missing (Gaps Identified from Research)

| Gap | Source | Impact |
|-----|--------|--------|
| System is empty -- never been activated | Exploration | Critical |
| No temporal validity on facts | Zep/Graphiti | High |
| No contradiction-preserving updates | Mem0, neuro-symbolic research | High |
| No confidence/freshness scoring | FPF paper, OpenMemory | Medium |
| No knowledge decay model | Context Rot research | Medium |
| No hybrid search (BM25 + vector) | QMD, multiple tools | Medium (needed at scale) |
| No entity-relation graph layer | Anthropic MCP memory, Cognee | Medium |
| No active gap detection | ALIGNAgent research | Low-Medium |
| No multi-resolution views | MemGAS, HiRetrieval | Low |
| No provenance chain (article -> source line) | MIT Data Provenance | Low |
| Query answers don't file back automatically | Karpathy pattern | Low |
| No dream/consolidation cycle | OpenClaw Auto-Dream | Aspirational |

---

## Recommended Improvements (Prioritized)

### Phase 1: Activate & Bootstrap (Immediate)

**Goal:** Get the existing system producing value today.

1. **Seed the first daily log manually** -- Write a `daily/2026-04-09.md` capturing key decisions from recent sessions (bittensor integration, trading engine architecture, knowledge system design).

2. **Run first compilation** -- `uv run python scripts/compile.py` to produce the first batch of articles and populate the index.

3. **Run first lint** -- `uv run python scripts/lint.py --structural-only` to validate system health.

4. **Verify hooks are firing** -- Check `scripts/flush.log` after a session to confirm the capture pipeline is active.

**Files:** `.claude/knowledge/daily/2026-04-09.md` (new), verify existing scripts work

---

### Phase 2: Temporal Validity & Freshness (High Value, Low Effort)

**Goal:** Facts know when they're stale.

Inspired by: Zep/Graphiti bi-temporal model, FPF epistemic status tracking, Context Rot research.

5. **Add temporal metadata to article frontmatter:**
   ```yaml
   confidence: 0.9          # 0.0-1.0, decays over time
   valid_from: 2026-04-09   # when this became true
   valid_until: null         # null = still valid, date = superseded
   superseded_by: null       # link to replacement article
   decay_rate: slow          # fast (days), medium (weeks), slow (months)
   ```

6. **Update AGENTS.md schema** to document these fields and instruct the compiler to set them.

7. **Update compile.py prompt** to:
   - Set `confidence` based on source count and specificity
   - Set `decay_rate` based on topic domain (trading signals = fast, architecture decisions = slow)
   - Check existing articles for supersession when creating new ones on the same topic

8. **Update lint.py** to add a "stale confidence" check -- flag articles where `confidence * decay_factor(age)` drops below 0.5.

**Files:** `AGENTS.md`, `scripts/compile.py`, `scripts/lint.py`, article templates

---

### Phase 3: Contradiction Detection (High Value, Medium Effort)

**Goal:** New facts don't silently overwrite old ones.

Inspired by: Mem0 contradiction resolution, neuro-symbolic conflict-aware learning, Karpathy's lint operation.

9. **Add a contradiction-check step to compile.py:**
   - Before updating an existing article, compare new claims against existing content
   - If contradiction detected: create a `contradictions/` log entry instead of overwriting
   - Format: `{ old_claim, new_claim, source_old, source_new, resolution: "pending" }`

10. **Add a `knowledge/contradictions/` directory** for unresolved conflicts.

11. **Update lint.py contradiction check** to surface unresolved items and suggest resolutions.

**Files:** `scripts/compile.py`, `AGENTS.md`, `scripts/lint.py`

---

### Phase 4: SQLite FTS5 Search Layer (Medium Value, Medium Effort)

**Goal:** Scale beyond index.md when article count grows past ~200.

Inspired by: QMD hybrid search, FabsWill article's SQLite FTS5 approach.

12. **Create `scripts/search.py`** -- SQLite FTS5 full-text search over all articles:
    - Build/update FTS5 index from article markdown files
    - CLI: `uv run python scripts/search.py "bittensor weight setting"`
    - Returns ranked results with snippets
    - No external dependencies (SQLite is stdlib)

13. **Wire into query.py** as a fallback when index.md exceeds context budget.

14. **Optional: Add as MCP tool** so any Claude Code session can search the knowledge base.

**Files:** `scripts/search.py` (new), `scripts/query.py` (update)

---

### Phase 5: Entity-Relation Graph (Medium Value, Higher Effort)

**Goal:** Enable graph traversal for "find all knowledge related to X."

Inspired by: Anthropic MCP memory server, Cognee, Aider repo-map.

15. **Create `scripts/graph.py`** -- lightweight entity-relation tracker:
    - Parse wikilinks from all articles to build an adjacency graph
    - Store as JSON or SQLite (entity -> relations -> entity)
    - CLI: `uv run python scripts/graph.py related "bittensor"` returns all connected articles
    - CLI: `uv run python scripts/graph.py orphans` finds disconnected knowledge

16. **Add code-knowledge mapping** -- track which articles discuss which code files:
    - Parse code file references from articles
    - When code changes (git diff), flag articles that may need updating
    - Inspired by Aider's repo-map but inverted (knowledge -> code)

**Files:** `scripts/graph.py` (new), `scripts/lint.py` (update)

---

### Phase 6: Dream Cycle & Active Learning (Aspirational)

**Goal:** Knowledge base that improves itself.

Inspired by: OpenClaw Auto-Dream, LangMem procedural memory, ALIGNAgent gap detection.

17. **Weekly consolidation script** (`scripts/dream.py`):
    - Score all articles by: access frequency, recency, confirmation count, cross-references
    - Promote high-value session log fragments that weren't captured as articles
    - Archive low-scoring articles past their decay window
    - Identify topic gaps (referenced concepts without their own articles)
    - Generate "suggested learning" list

18. **Procedural memory extraction** (LangMem-inspired):
    - If 3+ articles contain the same debugging pattern or workflow, propose a new CLAUDE.md rule
    - Closes the loop: knowledge capture -> behavioral change

**Files:** `scripts/dream.py` (new), potentially CLAUDE.md updates

---

## Novel Ideas (Brainstormed)

Beyond what any existing tool does:

### A. Trading-Aware Knowledge Decay
Different knowledge categories decay at different rates. Trading signals are stale in minutes; market regime assessments in hours; architectural decisions in months. The knowledge system should have domain-specific TTLs:
- `signal_knowledge`: 1 hour TTL
- `market_regime`: 24 hour TTL  
- `architecture`: 90 day TTL
- `tooling`: 30 day TTL

### B. Signal-Knowledge Feedback Loop
The trading engine's `SignalBus` already publishes signals. A knowledge listener on the bus could:
- Capture regime transitions as knowledge events
- Record trade outcomes linked to the signals that triggered them
- Build a compounding record of "what worked when"

### C. Bidirectional Code-Knowledge Sync
When code changes, the knowledge base should know. When knowledge changes, the code should be flagged:
- Git post-commit hook checks: did this commit touch files discussed in any knowledge article?
- If yes, flag those articles for review
- Inverse: when compiling new knowledge about a code pattern, check if the code still matches

### D. Confidence-Weighted Retrieval
Instead of treating all articles equally during query, weight by confidence score:
- High-confidence, recently-confirmed articles rank higher
- Stale or contradicted articles are included but flagged
- Query results show confidence alongside content

### E. Multi-Session Narrative
Track not just individual facts but the narrative arc of a project:
- "We started with approach A, hit problem B, pivoted to C"
- Captures the evolution of understanding, not just the final state
- Useful for onboarding and for understanding why current decisions were made

---

## Verification Plan

After each phase:
1. **Phase 1:** `cat .claude/knowledge/articles/index.md` -- should have entries. `ls .claude/knowledge/articles/concepts/` -- should have files.
2. **Phase 2:** Check a compiled article has temporal frontmatter fields. Run lint -- should report stale confidence items if any.
3. **Phase 3:** Manually create a contradicting daily log entry, compile, verify contradiction is flagged not silently overwritten.
4. **Phase 4:** `uv run python scripts/search.py "bittensor"` -- should return ranked results.
5. **Phase 5:** `uv run python scripts/graph.py related "bittensor"` -- should return connected articles.
6. **Phase 6:** `uv run python scripts/dream.py` -- should produce a consolidation report.

---

## Coordination with Gemini (TradingView MCP Integration)

Gemini produced `docs/superpowers/specs/2026-04-09-tradingview-mcp-integration-design.md` covering:
- **Companion App** -- TradingView CDP bridge -> Redis
- **Snap-Back Scalping** -- RSI(3) + VWAP + EMA(8) + BB Width + 1.5% distance filter
- **Persistent Memory Loop** -- Session bias -> Remembr.dev (this project) -> router integration

**Division of labor:**

| Workstream | Owner | Scope |
|------------|-------|-------|
| Knowledge system (Phases 1-6 + novel ideas) | Claude (this plan) | `.claude/knowledge/`, AGENTS.md, compile/lint/search/graph/dream scripts |
| Snap-Back strategy + VWAP indicator | Gemini | `trading/strategies/snapback_scalper.py`, `trading/data/indicators.py` (add `compute_vwap()`), `trading/trading_rules.yaml` |
| Bias-alignment filtering | Gemini | `trading/agents/router.py` -- block signals misaligned with session bias |
| Companion App (TradingView bridge) | **HOLD** | Defer until knowledge infrastructure is in place; design to plug into knowledge system |

**Flags for Gemini's spec:**
1. Remembr.dev IS this project (merged) -- references are correct
2. Replace "Laravel Memory API" references with FastAPI trading engine (Laravel is deprecated per TP-013)
3. Session bias should persist via `trading/brief/session_bias.py` -> knowledge daily log

**Integration point:** Gemini's Snap-Back strategy produces trading decisions that flow through `SignalBus` -> `OpportunityRouter`. The knowledge system's Signal-Knowledge Feedback Loop (Novel Idea B) captures those decisions as knowledge events, closing the loop.

---

## Phase 7: Remembr.dev Domain & URL Setup

**Goal:** Get remembr.dev properly configured as the public-facing URL for this project's memory API.

**Current state:**
- Deployed on **Railway** (multi-service: api, trading, frontend, redis)
- SDK hardcodes `https://remembr.dev/api/v1` as default base URL
- Vendored SDK at `trading/vendor/remembr-sdk/`
- Cloudflare in place for WhatsApp integration — keep it
- No CORS middleware on FastAPI (relies on Nginx/Railway proxy)
- Railway handles SSL/TLS termination automatically

**Tasks:**

19. **Configure Railway custom domain** — Point `remembr.dev` to the Railway frontend service. Railway auto-provisions SSL certs for custom domains.

20. **Set up API routing** — Ensure `remembr.dev/api/v1/*` routes to the FastAPI trading engine (not Laravel). The Nginx config currently proxies `/api` to Laravel — update for FastAPI as the primary API.

21. **Add CORS middleware to FastAPI** — Currently missing. Add `CORSMiddleware` with allowed origins including `https://remembr.dev` and `http://localhost:3000` (dev).

22. **Make base URL configurable** — Add `STA_REMEMBR_BASE_URL` env var to `trading/config.py` so the SDK default can be overridden per environment (dev vs staging vs prod).

23. **Verify Cloudflare DNS** — Confirm `remembr.dev` DNS records point to Railway (CNAME or A record), with Cloudflare proxying enabled for WhatsApp webhook routes only.

24. **Health check endpoint** — Ensure `remembr.dev/health` and `remembr.dev/ready` work through the full proxy chain.

**Files:** `nginx.conf`, `trading/config.py`, `trading/api/app.py`, `railway.json`, Cloudflare DNS dashboard

---

## Implementation Notes

- Implementation will run via **Claude CLI on WSL Ubuntu** (not Windows/Git Bash)
- All paths should use Linux-native paths (`/opt/agent-memory-unified/...`)
- Run scripts with `uv run python` from `.claude/knowledge/` directory
- Knowledge system venv is at `.claude/knowledge/.venv/`

---

## Key Files

| File | Role | Action |
|------|------|--------|
| `.claude/knowledge/AGENTS.md` | Schema/spec | Update with temporal fields, contradiction handling |
| `.claude/knowledge/scripts/compile.py` | Daily log -> articles | Add temporal metadata, contradiction detection |
| `.claude/knowledge/scripts/lint.py` | Health checks | Add freshness decay check |
| `.claude/knowledge/scripts/query.py` | Index-guided retrieval | Wire FTS5 fallback |
| `.claude/knowledge/scripts/search.py` | FTS5 search (NEW) | Create |
| `.claude/knowledge/scripts/graph.py` | Entity-relation graph (NEW) | Create |
| `.claude/knowledge/scripts/dream.py` | Consolidation cycle (NEW) | Create |
| `.claude/knowledge/index.md` | Master catalog | Will be auto-populated |
| `.claude/knowledge/daily/` | Raw session logs | Seed first entry |

---

## Research Sources

### Primary Sources
- [Karpathy LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) -- 13,344 stars, the foundational pattern
- [MindStudio article](https://www.mindstudio.ai/blog/andrej-karpathy-llm-wiki-knowledge-base-claude-code) -- Practical implementation guide
- [FabsWill article](https://fabswill.com/blog/building-a-second-brain-that-compounds-karpathy-obsidian-claude/) -- Compounding second brain with Obsidian + 4 Claude Code skills

### Alternative Tools Surveyed
- **QMD** (Tobi Lutke) -- Local BM25 + vector hybrid search, AST-aware code chunking
- **Mem0** -- Triple-store memory (vector + graph + KV), 26% accuracy boost over OpenAI
- **Letta/MemGPT** -- Self-editing tiered memory (core/recall/archival)
- **Cognee** -- Knowledge graph + vector embeddings, multi-hop reasoning
- **Zep/Graphiti** -- Bi-temporal knowledge graph, best-in-class temporal retrieval
- **Cursor .mdc** -- Modular rules files (evolved from monolithic .cursorrules)
- **Aider repo-map** -- PageRank on dependency graph for context selection
- **claude-memory-compiler** -- Closest analog to this project's system
- **OpenClaw Auto-Dream** -- Sleep-cycle memory consolidation with importance scoring
- **LangMem** -- Procedural memory (auto-rewrites system prompt from learned patterns)

### Academic Papers
- "Memory in the Age of AI Agents" (Dec 2025) -- 59 co-author survey
- "A-MEM: Agentic Memory" (NeurIPS 2025) -- Zettelkasten-inspired indexing
- "MemOS" (2025) -- Memory-as-OS with MemCube abstraction
- "FPF: Epistemic Status Tracking" (Jan 2026) -- Confidence aggregation via Godel t-norm
- "Causal Graphs Meet Thoughts" (Jan 2025) -- Cause-effect retrieval alignment
- "MemGAS" (2025) -- Entropy-based granularity routing

### TradingView MCP Integration
- [jackson-video-resources/claude-tradingview-mcp-trading](https://github.com/jackson-video-resources/claude-tradingview-mcp-trading) -- Trading bot + TradingView MCP bridge
- Gemini spec: `docs/superpowers/specs/2026-04-09-tradingview-mcp-integration-design.md`
