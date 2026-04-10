# MemPalace Integration — Design Spec

**Status:** Approved  
**Date:** 2026-04-08  
**Source:** [milla-jovovich/mempalace](https://github.com/milla-jovovich/mempalace) v3.0.14  
**Context:** Integrating MemPalace patterns into agent-memory-unified to add temporal awareness, layered context, and operational cost reduction.

---

## Overview

Three workstreams, executed in order:

1. **MCP Operational Conventions** — Establish wing/room taxonomy and KG entity conventions for cross-session memory via the already-installed MemPalace MCP server. No code changes.
2. **Sprint 1: Small High-Value Ports** — Content-hash dedup, pattern pre-filter for flush.py, WAL journaling. ~200 lines of new code.
3. **Sprint 2: Temporal KG + Layered Agent Context** — Port MemPalace's knowledge graph into the trading engine, implement L0+L1 context layers for LLM agents. ~600 lines of new code.

### Dependency Graph

```
Sprint 1:
  2A (dedup)        — independent
  2B (pre-filter)   — independent
  2C (WAL)          — independent, but must complete before Sprint 2

Sprint 2:
  3A (KG)           — depends on 2C (WAL)
  3B (layers)       — independent of 3A, but optionally enriched by KG
  3A and 3B can be built in parallel
```

---

## Workstream 1: MCP Operational Conventions

No code changes. Establishes conventions for filing memories via MemPalace MCP tools across Claude and Gemini sessions.

### 1.1 Wing/Room Taxonomy

| Wing             | Rooms                                                  | What Goes Here                                                     |
|------------------|--------------------------------------------------------|--------------------------------------------------------------------|
| `trading`        | `strategies`, `regimes`, `incidents`, `decisions`, `performance` | Trading engine operations, strategy tuning, market conditions      |
| `bittensor`      | `miners`, `weights`, `bridge`, `subnet8`, `validators` | Miner reliability, weight-setting, Taoshi bridge observations      |
| `infrastructure` | `docker`, `database`, `deploy`, `monitoring`           | DevOps decisions, deployment issues, config changes                |
| `project`        | `roadmap`, `architecture`, `adr`, `retrospectives`     | High-level project decisions, ADRs, sprint retrospectives          |
| `agents`         | `collaboration`, `presence`, `tasks`                   | Inter-agent relationships, delegation patterns, workflow observations |

### 1.2 Knowledge Graph Entity Types

| Entity Type     | Examples                       | Predicates                                                  |
|-----------------|--------------------------------|-------------------------------------------------------------|
| `market_regime` | `btc_regime`, `eth_regime`     | `in_state` (bull/bear/range), `volatility` (high/low)      |
| `miner`         | `miner_uid_144`, `miner_uid_22` | `reliable_on` (pair), `flagged_for` (reason), `alpha_on` (pair) |
| `strategy`      | `rsi_scanner`, `kalshi_news_arb` | `performing_in` (regime), `disabled_because` (reason)      |
| `incident`      | `bridge_outage_apr8`           | `caused_by`, `resolved_by`, `affected`                     |

### 1.3 Filing Strategy ("Memory Sieve")

Post-session batching via MemPalace's auto-save hooks:

1. **Identify change deltas:** Did the session produce a strategy change, incident resolution, or architecture decision?
2. **Thematic grouping:** Synthesize multiple small events into a single high-signal observation.
3. **Dedup discipline:** Before adding drawers, run `mempalace_check_duplicate(content, threshold=0.85)`.

### 1.4 Retrieval Strategy (Hybrid Contextual Pull)

At session start, tier the retrieval:

1. **State snapshot (mandatory):** `mempalace_kg_query` on current `market_regime`, active `strategy` statuses, any active `incident`.
2. **Targeted search:** Scoped `mempalace_search(query, wing, limit=3)` based on the session topic.
3. **Proactive deep-dive:** If snapshot shows an active incident, pull the full `mempalace_kg_timeline(entity)`.

### 1.5 Agent Diaries

- `mempalace_diary_write(agent_name="claude_trading", entry="...", topic="debugging")` for observations that don't fit the KG.
- `mempalace_diary_read(agent_name="claude_trading", last_n=5)` at session start.

### 1.6 Usage Examples

```
# File a trading decision
mempalace_add_drawer(wing="trading", room="decisions",
    content="Disabled kalshi_theta during low-vol regime — theta decay insufficient to cover spread costs. Re-enable when VIX > 18.")

# Record regime change
mempalace_kg_add(subject="btc_regime", predicate="in_state", object="accumulation", valid_from="2026-04-08")
mempalace_kg_invalidate(subject="btc_regime", predicate="in_state", object="bear", ended="2026-04-07")

# Query before architecture decisions
mempalace_search(query="miner reliability subnet 8", wing="bittensor")
mempalace_kg_query(entity="rsi_scanner", direction="both")
mempalace_kg_timeline(entity="btc_regime")
```

---

## Workstream 2: Sprint 1 — Small High-Value Ports

Three independent changes. Each can be implemented, tested, and merged separately.

### 2A. Content-Hash Dedup in LocalMemoryStore

**File:** `trading/storage/memory.py`

**Problem:** `store()` generates a new UUID every call. Identical trade memories accumulate — same lesson stored after similar trades.

**Solution:** MD5 content hash with UNIQUE index. Duplicate writes become access-count increments.

**Schema change:**
```sql
ALTER TABLE memories ADD COLUMN content_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash);
```

Migration is idempotent: `ALTER TABLE ... ADD COLUMN` wrapped in try/except (SQLite doesn't support `IF NOT EXISTS` on ALTER).

**Changes to `store()`:**
```python
import hashlib

async def store(self, value, ...):
    content_hash = hashlib.md5(value.encode()).hexdigest()  # Full 32-char hash
    
    # Check for existing
    existing = await self._db.execute_fetchone(
        "SELECT id, access_count FROM memories WHERE content_hash = ?",
        (content_hash,)
    )
    if existing:
        await self._db.execute(
            "UPDATE memories SET access_count = access_count + 1, updated_at = ? WHERE id = ?",
            (now_iso(), existing["id"])  # updated_at prevents "stale memory" appearance
        )
        return {"id": existing["id"], "deduplicated": True, ...}
    
    # Normal insert with content_hash
    ...
```

**New method:**
```python
async def check_duplicate(self, value: str) -> MemoryRecord | None:
    content_hash = hashlib.md5(value.encode()).hexdigest()
    row = await self._db.execute_fetchone(
        "SELECT * FROM memories WHERE content_hash = ?", (content_hash,)
    )
    return self._row_to_record(row) if row else None
```

**Design decisions:**
- Full 32-char MD5 stored (not truncated) — clean audit trail, negligible storage difference.
- UNIQUE index provides database-level idempotency even under concurrent async writes.
- `access_count` increment on dedup turns redundancy into importance signal.
- No changes to callers (`memory_client.py`, `trade_reflector.py`). Dedup is transparent.

**Tests:**
- Store same value twice → second call returns `deduplicated: True`, `access_count` = 2.
- Store different values with same tags → both stored (different hashes).
- `check_duplicate()` returns existing record or None.
- Concurrent `store()` of same content → one INSERT, one UPDATE (no constraint violation).

---

### 2B. Pattern Pre-Filter in flush.py

**File:** `.claude/knowledge/scripts/flush.py`

**Problem:** Every session end spawns an LLM call ($0.02-0.05) even for sessions that were pure file reads or git commands. ~30-50% of flushes produce `FLUSH_OK` (nothing worth saving).

**Solution:** Lightweight keyword pre-filter that skips the LLM call if no knowledge-bearing patterns are found.

**New function (~80 lines):**
```python
import re

# Borrowed from MemPalace general_extractor.py, adapted for our domain
DECISION_MARKERS = [
    "decided", "let's use", "go with", "switched to", "trade-off",
    "chose", "architecture", "we went with", "settled on", "approach",
]
PROBLEM_MARKERS = [
    "bug", "broke", "error", "root cause", "fix", "workaround",
    "crashed", "doesn't work", "issue", "regression",
]
MILESTONE_MARKERS = [
    "it works", "shipped", "deployed", "figured out", "breakthrough",
    "fixed", "solved", "nailed it", "released",
]
LESSON_MARKERS = [
    "learned", "gotcha", "turns out", "important to note", "the trick is",
    "key insight", "remember that", "lesson",
]
CONFIG_MARKERS = [
    "env var", "config", "setting", "enabled", "disabled", "toggled",
    "migration", "schema change",
]

# Lines that are pure tool noise
NOISE_PATTERNS = [
    re.compile(r"^\*\*(Read|Glob|Bash|Grep|Write|Edit)\*\*"),
    re.compile(r"^\[File contents?\]"),
    re.compile(r"^\*\*(User|Assistant)\*\*:\s*(yes|no|y|n|ok|okay|continue|next|thanks?)\s*$", re.I),
    re.compile(r"\x1b\[[0-9;]*m"),  # ANSI escape codes
]

def has_knowledge_signal(context: str) -> bool:
    """Returns True if context contains patterns worth an LLM extraction call."""
    # Strip noise lines
    lines = context.splitlines()
    clean_lines = [l for l in lines if not any(p.search(l) for p in NOISE_PATTERNS)]
    clean_text = "\n".join(clean_lines).lower()
    
    # Explicit user hints always trigger
    if "user hint:" in clean_text or "remember this" in clean_text:
        return True
    
    # Silent refactor heuristic: significant file creation or heavy editing
    # Write (new file) is higher signal than Edit (incremental change)
    write_count = sum(1 for l in lines if re.match(r"^\*\*Write\*\*", l))
    edit_count = sum(1 for l in lines if re.match(r"^\*\*Edit\*\*", l))
    if write_count >= 1 or edit_count > 3:
        return True
    
    # Check all marker lists
    all_markers = (DECISION_MARKERS + PROBLEM_MARKERS + MILESTONE_MARKERS
                   + LESSON_MARKERS + CONFIG_MARKERS)
    matches = sum(1 for m in all_markers if m in clean_text)
    
    return matches >= 2  # Require at least 2 marker hits to avoid false positives
```

**Integration point** (in existing flush logic, after reading context, before LLM call):
```python
context = read_context_file(context_path)

if not has_knowledge_signal(context):
    logging.info("Skipping flush: no knowledge signals in %d-char context", len(context))
    cleanup_temp_file(context_path)
    return

# Existing LLM extraction call follows...
```

**Design decisions:**
- Threshold of 2+ markers avoids false positives (a single "error" in tool output shouldn't trigger).
- "Silent refactor" heuristic (>3 writes) catches sessions with no discussion but significant code changes.
- ANSI escape code stripping prevents terminal artifacts from polluting keyword matching.
- `"User hint:"` and `"remember this"` always trigger — explicit user signals are high-value.

**Expected impact:** ~30-40% fewer LLM calls. Conservative — only skips sessions with zero meaningful markers.

**Tests:**
- Context with only `Read` / `Glob` / `git status` → `has_knowledge_signal() == False`.
- Context with "decided to switch to WAL mode" → True (1 decision + 1 config marker).
- Context with 4 `Edit` calls but no keywords → True (silent refactor heuristic).
- Context with "User hint: remember this config" → True (explicit hint).
- Empty context → False.

---

### 2C. WAL Journaling + Busy Timeout

**Files:** `trading/storage/memory.py`, `trading/api/app.py` (prompt store DB creation), new `trading/storage/knowledge_graph.py` (Sprint 2)

**Problem:** SQLite defaults to rollback journal. Under concurrent agent reads/writes, this causes "database is locked" errors.

**Solution:** Two pragmas after every `aiosqlite.connect()`:
```python
await db.execute("PRAGMA journal_mode=WAL")
await db.execute("PRAGMA busy_timeout=5000")
```

**Changes:**

1. **`trading/storage/memory.py` → `connect()`:** Add both pragmas after table creation.
2. **`trading/api/app.py`:** Wherever `aiosqlite.connect()` is called for the prompt store or other DBs, add both pragmas.
3. **Sprint 2's `knowledge_graph.py`:** Built with WAL + busy_timeout from day one.

**Why busy_timeout=5000:**
- WAL allows concurrent readers during writes, but checkpoint operations still briefly lock.
- 5000ms (5s) is generous — our write operations complete in <100ms. This prevents spurious "database is locked" errors during high-frequency poll cycles (evaluator + weight_setter reading while bridge writes).

**Verification:** After implementation, run a concurrent stress test — 2 async tasks writing to the same DB while 3 read. Confirm zero lock errors.

**Tests:**
- Verify `PRAGMA journal_mode` returns `wal` after connect.
- Concurrent write test: 10 simultaneous `store()` calls → all succeed, no lock errors.

---

## Workstream 3: Sprint 2 — Temporal KG + Layered Agent Context

Two features that can be built in parallel. KG enriches layers when available, but layers work without it.

### 3A. Temporal Knowledge Graph for Trading

**New file:** `trading/storage/knowledge_graph.py` (~250 lines)

**Ported from:** MemPalace `knowledge_graph.py` (~350 lines), adapted for async + trading domain.

#### Schema

```sql
CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,           -- lowercase, underscores (e.g., "miner_uid_144")
    name TEXT NOT NULL,            -- display name (e.g., "Miner UID 144")
    entity_type TEXT DEFAULT 'unknown',
    properties TEXT DEFAULT '{}',  -- JSON blob for extensible metadata
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS kg_triples (
    id TEXT PRIMARY KEY,           -- t_{subject_id}_{predicate}_{object_id}_{8-char-hash}
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    valid_from TEXT,               -- ISO date, NULL = always valid from past
    valid_to TEXT,                 -- ISO date, NULL = currently valid
    confidence REAL DEFAULT 1.0,   -- 0.0-1.0, set by source component
    source TEXT,                   -- "bridge" | "evaluator" | "weight_setter" | "regime_manager" | "manual"
    properties TEXT DEFAULT '{}',  -- JSON blob for extensible relationship metadata (e.g., alpha/beta inputs for weight decisions)
    invalidation_reason TEXT,      -- populated by invalidate(), NULL = still valid
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject) REFERENCES kg_entities(id),
    FOREIGN KEY (object) REFERENCES kg_entities(id)
);

CREATE INDEX IF NOT EXISTS idx_kg_triples_subject ON kg_triples(subject);
CREATE INDEX IF NOT EXISTS idx_kg_triples_object ON kg_triples(object);
CREATE INDEX IF NOT EXISTS idx_kg_triples_predicate ON kg_triples(predicate);
CREATE INDEX IF NOT EXISTS idx_kg_triples_valid ON kg_triples(valid_from, valid_to);

PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
```

**Entity types:** `market_regime`, `miner`, `strategy`, `pair`, `incident`

#### Class: `TradingKnowledgeGraph`

```python
class TradingKnowledgeGraph:
    def __init__(self, db_path: str = "data/knowledge_graph.sqlite3"):
        ...

    async def connect(self) -> None:
        """Open DB, create tables, set WAL + busy_timeout."""

    async def close(self) -> None:
        """Close DB connection."""

    def _entity_id(self, name: str) -> str:
        """Normalize: lowercase, spaces→underscores, strip apostrophes."""

    async def add_entity(self, name: str, entity_type: str = "unknown",
                         properties: dict | None = None) -> str:
        """Add or update entity. Returns entity ID. Idempotent."""

    async def add_triple(self, subject: str, predicate: str, obj: str,
                         valid_from: str | None = None,
                         valid_to: str | None = None,
                         confidence: float = 1.0,
                         source: str | None = None,
                         properties: dict | None = None) -> str:
        """Add relationship triple. Auto-creates entities. Returns triple ID.
        Checks for existing identical triple to avoid dupes."""

    async def invalidate(self, subject: str, predicate: str, obj: str,
                         ended: str | None = None,
                         reason: str | None = None) -> None:
        """Mark relationship as no longer valid.
        Sets valid_to = ended (default: today).
        Sets invalidation_reason = reason (e.g., 'high_latency', 'manual_blacklist')."""

    async def query_entity(self, name: str, as_of: str | None = None,
                           direction: str = "outgoing") -> list[dict]:
        """Get all relationships for entity.
        direction: 'outgoing' (subject→), 'incoming' (→object), 'both'.
        Temporal filter: (valid_from IS NULL OR valid_from <= as_of)
                     AND (valid_to IS NULL OR valid_to >= as_of)."""

    async def query_relationship(self, predicate: str,
                                 as_of: str | None = None) -> list[dict]:
        """Get all triples with given predicate, optionally filtered by time."""

    async def timeline(self, entity_name: str | None = None,
                       limit: int = 100) -> list[dict]:
        """Chronological list of facts. If entity_name provided, filters.
        Ordered by valid_from ASC NULLS LAST.
        Includes invalidation_reason in results."""

    async def stats(self) -> dict:
        """Returns {entities, triples, current_facts, expired_facts, relationship_types}."""
```

#### Integration: 4 Writers

**Writer 1: TaoshiBridge** (`trading/integrations/bittensor/taoshi_bridge.py`)

After each poll cycle:
```python
# Record miner activity
for miner_hotkey, signals in new_signals.items():
    await self._kg.add_triple(
        f"miner_{miner_hotkey[:8]}", "active_on", "subnet8",
        valid_from=now_iso(), confidence=signal_quality, source="bridge"
    )
    for signal in signals:
        await self._kg.add_triple(
            f"miner_{miner_hotkey[:8]}", "signal_on", signal.pair,
            valid_from=now_iso(), confidence=signal.confidence, source="bridge"
        )

# When miner stops sending
await self._kg.invalidate(
    f"miner_{hotkey[:8]}", "active_on", "subnet8",
    ended=now_iso(), reason="no_signals_3_cycles"
)
```

**Writer 2: Evaluator** (`trading/integrations/bittensor/evaluator.py`)

After scoring predictions:
```python
# Record evaluation outcome
await self._kg.add_triple(
    f"miner_{hotkey[:8]}", "accuracy_on", pair,
    valid_from=window_start, valid_to=window_end,
    confidence=accuracy_score, source="evaluator"
)
```

Before scoring — temporal context query:
```python
# What was the regime when this prediction was made?
regime_facts = await self._kg.query_entity("btc_regime", as_of=prediction_time)
miner_history = await self._kg.query_entity(f"miner_{hotkey[:8]}", as_of=prediction_time)
```

**Writer 3: WeightSetter** (`trading/integrations/bittensor/weight_setter.py`)

After setting weights:
```python
for uid, weight in weights.items():
    await self._kg.add_triple(
        f"miner_uid_{uid}", "weight_set_to", str(round(weight, 4)),
        valid_from=now_iso(), source="weight_setter"
    )
```

**Writer 4: RegimeManager** (`trading/learning/regime_manager.py` or equivalent)

On regime transitions:
```python
# Invalidate old regime
await self._kg.invalidate(
    "btc_regime", "in_state", old_state,
    ended=now_iso(), reason=f"transition_to_{new_state}"
)
# Record new regime
await self._kg.add_triple(
    "btc_regime", "in_state", new_state,
    valid_from=now_iso(), source="regime_manager"
)
await self._kg.add_triple(
    "btc_regime", "volatility", vol_level,
    valid_from=now_iso(), source="regime_manager"
)
```

#### Initialization

In `trading/api/app.py` lifespan:
```python
from storage.knowledge_graph import TradingKnowledgeGraph

kg = TradingKnowledgeGraph(db_path="data/knowledge_graph.sqlite3")
await kg.connect()

# Inject into consumers
bridge = TaoshiBridge(..., knowledge_graph=kg)
evaluator = Evaluator(..., knowledge_graph=kg)
weight_setter = WeightSetter(..., knowledge_graph=kg)
regime_manager = RegimeManager(..., knowledge_graph=kg)
```

Single instance, shared across all consumers. WAL + busy_timeout handles concurrent access.

#### API Endpoints

Add to `trading/api/routes/bittensor.py`:
```
GET /api/bittensor/kg/entity/{name}?as_of=...&direction=both
GET /api/bittensor/kg/timeline?entity=...&limit=50
GET /api/bittensor/kg/stats
```

Read-only endpoints for the frontend dashboard. No auth beyond existing `X-API-Key`.

---

### 3B. Layered Agent Context (L0 + L1)

**Files modified:** `trading/learning/prompt_store.py`, `trading/agents/base.py`, `trading/agents/runner.py`

#### New Table

Added to `SqlPromptStore` schema:
```sql
CREATE TABLE IF NOT EXISTS agent_context_cache (
    agent_name TEXT PRIMARY KEY,
    l0_text TEXT NOT NULL,
    l1_text TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    trade_count INTEGER DEFAULT 0
);
```

Cache only — regenerated on demand, not a source of truth.

#### L0 — Agent Identity (~50-100 tokens)

Static, derived from `agents.yaml` config. Generated once at startup, never changes unless config changes.

```
## Identity
Agent: rsi_scanner | Strategy: RSI momentum | Action: suggest_trade
Universe: AAPL, MSFT, GOOGL, AMZN | Schedule: continuous (60s)
Trust: monitored | Description: Scans for RSI divergence signals on equity universe.
```

**Source:** `AgentConfig` dataclass fields (name, strategy, description, universe, action_level, trust_level, schedule).

#### L1 — Essential Performance Story (~200-500 tokens)

Auto-generated from trade memory. Refreshed after deep reflections with 30-minute debounce.

```
## Recent Performance (auto-generated, 2026-04-08)
Regime: accumulation (since 2026-04-01)

Wins (7 in current regime):
  Best: AAPL +$340 — strong RSI divergence, high volume confirmation
  2nd: MSFT +$215 — clean breakout, regime-aligned momentum

Losses (3 in current regime):
  Worst: MSFT -$180 — false breakout during regime transition
  2nd: GOOGL -$95 — low volume, signal below threshold

Key pattern: RSI divergence signals unreliable during regime transitions.
Win rate in accumulation: 70% (7/10)
```

**Generation logic (`generate_agent_context`):**
1. Query recent trades via `reflector.query(symbol="", context="recent trades performance", agent_name=name, top_k=20)` (empty symbol matches broadly; if the existing `query()` method requires a specific symbol, add a `query_all(agent_name, top_k)` convenience method to TradeReflector)
2. **Empty-state guard:** If query returns zero trades (brand new agent), set L1 to `"## Recent Performance\nNew agent — no historical trades recorded yet. Operating without performance context."` and skip steps 3-6.
3. If KG available: query current regime via `kg.query_entity("btc_regime")`, filter trades to matching regime
4. If KG unavailable: use all trades, skip regime annotation
5. Sort by absolute P&L, take top 5 wins + top 5 losses
6. Extract key pattern from `PromptStore` lessons
7. Format as compact markdown (~200-500 tokens)

#### Integration in LLMAgent

**`trading/agents/base.py`:**
```python
class LLMAgent(Agent):
    @property
    def system_prompt(self) -> str:
        base = self._config.system_prompt or ""
        context = ""
        if self._prompt_store:
            # L0 + L1 (new)
            agent_ctx = self._prompt_store.get_agent_context(self.name)
            if agent_ctx:
                context = agent_ctx
            # Existing: learned rules
            learned = self._prompt_store.get_runtime_prompt(self.name)
            if learned:
                context = f"{context}\n\n{learned}" if context else learned
        return f"{base}\n\n{context}" if context else base
```

**Separation of concerns:**
- `LLMAgent.system_prompt` → Internal state (L0 identity + L1 performance + learned rules)
- `AgentRunner._execute_scan` → Environment state (symbol context, session bias, ticker data)
- AgentRunner does NOT become a god object.

#### Regeneration Triggers

**`trading/agents/runner.py` → `start_agent()`:**
```python
async def start_agent(self, name: str):
    agent = self._agents[name]
    
    # Prime L0+L1 context on startup (no cold starts)
    if self._prompt_store and self._trade_reflector_factory:
        reflector = await self._trade_reflector_factory(name)
        await self._prompt_store.generate_agent_context(
            agent_name=name,
            agent_config=agent._config,
            reflector=reflector,
            knowledge_graph=self._knowledge_graph,  # optional
        )
    
    await agent.setup()
    ...
```

**`trading/learning/trade_reflector.py` → `_reflect_deep()`:**
```python
async def _reflect_deep(self, trade, agent_name):
    # ... existing deep reflection logic ...
    
    # Trigger L1 regeneration (debounced)
    if self._prompt_store:
        await self._prompt_store.maybe_regenerate_context(
            agent_name=agent_name,
            reflector=self,
            knowledge_graph=self._knowledge_graph,
            min_interval_minutes=30,  # debounce
        )
```

**Debounce logic in `SqlPromptStore`:**
```python
async def maybe_regenerate_context(self, agent_name, reflector, knowledge_graph=None,
                                    min_interval_minutes=30):
    cached = await self._get_cached_context(agent_name)
    if cached:
        elapsed = (now() - parse_iso(cached["generated_at"])).total_seconds() / 60
        if elapsed < min_interval_minutes:
            return  # Too soon, skip
    await self.generate_agent_context(agent_name, ..., reflector=reflector,
                                       knowledge_graph=knowledge_graph)
```

#### Token Budget

| Component | Tokens | Source |
|-----------|--------|--------|
| L0 (Identity) | 50-100 | agents.yaml config |
| L1 (Performance) | 200-500 | Trade memory + KG regime |
| Learned rules | 100-300 | Existing PromptStore |
| **Total agent context** | **350-900** | Injected via system_prompt |

This replaces unbounded memory dumps with a fixed-budget, auto-curated context. LLM agents get the most relevant information in <1000 tokens.

---

## Testing Strategy

### Sprint 1 Tests

| Test | Location | Type |
|------|----------|------|
| Dedup: store same value twice → deduplicated | `tests/unit/test_local_memory.py` | unit |
| Dedup: concurrent stores → no constraint violation | `tests/unit/test_local_memory.py` | unit |
| Pre-filter: noise-only context → False | `tests/unit/test_flush_filter.py` | unit |
| Pre-filter: decision markers → True | `tests/unit/test_flush_filter.py` | unit |
| Pre-filter: silent refactor (>3 writes) → True | `tests/unit/test_flush_filter.py` | unit |
| WAL: concurrent reads + writes → no lock errors | `tests/unit/test_sqlite_wal.py` | unit |

### Sprint 2 Tests

| Test | Location | Type |
|------|----------|------|
| KG: add_triple + query_entity → returns fact | `tests/unit/test_knowledge_graph.py` | unit |
| KG: temporal filter — as_of excludes expired | `tests/unit/test_knowledge_graph.py` | unit |
| KG: invalidate sets valid_to + reason | `tests/unit/test_knowledge_graph.py` | unit |
| KG: timeline ordered by valid_from | `tests/unit/test_knowledge_graph.py` | unit |
| KG: concurrent writes (bridge + evaluator) | `tests/unit/test_knowledge_graph.py` | unit |
| L0: generated from AgentConfig | `tests/unit/test_agent_context.py` | unit |
| L1: top trades formatted correctly | `tests/unit/test_agent_context.py` | unit |
| L1: regime-filtered when KG available | `tests/unit/test_agent_context.py` | unit |
| L1: graceful fallback when KG unavailable | `tests/unit/test_agent_context.py` | unit |
| L1: debounce prevents regeneration within 30min | `tests/unit/test_agent_context.py` | unit |
| Integration: LLMAgent.system_prompt includes L0+L1 | `tests/unit/test_llm_agent.py` | unit |

---

## Files Changed Summary

### Sprint 1

| File | Change | Lines |
|------|--------|-------|
| `trading/storage/memory.py` | Add content_hash column, dedup in store(), check_duplicate() | +60 |
| `.claude/knowledge/scripts/flush.py` | Add has_knowledge_signal() pre-filter | +80 |
| `trading/storage/memory.py` | WAL + busy_timeout in connect() | +2 |
| `trading/api/app.py` | WAL + busy_timeout on prompt store DB | +2 |

### Sprint 2

| File | Change | Lines |
|------|--------|-------|
| `trading/storage/knowledge_graph.py` | **New file** — TradingKnowledgeGraph class | +250 |
| `trading/integrations/bittensor/taoshi_bridge.py` | Add KG writes after poll cycles | +30 |
| `trading/integrations/bittensor/evaluator.py` | Add KG queries before scoring, writes after | +40 |
| `trading/integrations/bittensor/weight_setter.py` | Add KG writes after weight setting | +15 |
| `trading/learning/regime_manager.py` | Add KG writes on regime transitions | +20 |
| `trading/learning/prompt_store.py` | Add agent_context_cache table, generate/get/maybe_regenerate methods | +120 |
| `trading/agents/base.py` | Update LLMAgent.system_prompt to include L0+L1 | +10 |
| `trading/agents/runner.py` | Call generate_agent_context() in start_agent() | +10 |
| `trading/learning/trade_reflector.py` | Trigger L1 regeneration after deep reflection | +5 |
| `trading/api/app.py` | Initialize KG, inject into consumers | +15 |
| `trading/api/routes/bittensor.py` | Add 3 KG read endpoints | +40 |

### Tests (New Files)

| File | Tests |
|------|-------|
| `tests/unit/test_knowledge_graph.py` | 5 tests |
| `tests/unit/test_agent_context.py` | 5 tests |
| `tests/unit/test_flush_filter.py` | 5 tests |
| `tests/unit/test_local_memory.py` (additions) | 3 tests |
| `tests/unit/test_sqlite_wal.py` | 1 test |

---

## Rollout Order

1. **Sprint 1 (parallel, any order):**
   - 2C: WAL + busy_timeout (smallest change, unblocks Sprint 2)
   - 2A: Content-hash dedup
   - 2B: Pattern pre-filter

2. **Sprint 2 (parallel after Sprint 1):**
   - 3A: Temporal KG + 4 writer integrations + API endpoints
   - 3B: Layered context (L0+L1) + regeneration triggers

3. **Validation:**
   - All unit tests pass
   - Manual verification: start trading engine, confirm KG populates from bridge polls
   - Manual verification: LLM agent system_prompt includes L0+L1 context
   - Concurrent stress test on KG database

---

## What We Explicitly Do NOT Build

- **AAAK dialect compression** — 84.2% retrieval vs 96.6% raw. Too lossy for trading decisions.
- **ChromaDB in trading engine** — Use MemPalace MCP for cross-session, pgvector for trading. Don't conflate.
- **Full graph traversal / tunnel detection** — Wait for KG to prove value before connecting agent namespaces.
- **Agent diary integration in trading engine** — Use via MCP tools only. No code coupling.
- **Automated KG seeding from historical data** — Manual seeding first. Automation is a future sprint.
