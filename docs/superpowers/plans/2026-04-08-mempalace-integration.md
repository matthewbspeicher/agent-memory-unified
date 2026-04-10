# MemPalace Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate MemPalace patterns into the trading engine — content-hash dedup, flush pre-filtering, WAL journaling, temporal knowledge graph, and layered agent context.

**Architecture:** Sprint 1 adds three independent hardening changes (~200 lines). Sprint 2 adds a temporal KG (`trading/storage/knowledge_graph.py`) and L0/L1 context layers in `prompt_store.py`, wired into the bittensor pipeline and LLM agent system prompts.

**Tech Stack:** Python 3.13, aiosqlite, SQLite WAL mode, hashlib (MD5), regex-based keyword matching

**Spec:** `docs/superpowers/specs/2026-04-08-mempalace-integration-design.md`

---

## File Map

### Sprint 1 — Files

| File | Action | Responsibility |
|------|--------|----------------|
| `trading/storage/memory.py` | Modify | Add content_hash column, dedup logic, WAL pragma |
| `.claude/knowledge/scripts/flush.py` | Modify | Add pattern pre-filter before LLM call |

### Sprint 2 — Files

| File | Action | Responsibility |
|------|--------|----------------|
| `trading/storage/knowledge_graph.py` | Create | Temporal KG with entities + triples tables |
| `trading/learning/prompt_store.py` | Modify | Add agent_context_cache table, L0/L1 generation |
| `trading/agents/base.py` | Modify | LLMAgent.system_prompt includes L0+L1 |
| `trading/agents/runner.py` | Modify | Prime agent context on startup |
| `trading/api/routes/bittensor.py` | Modify | Add 3 KG read endpoints |

### Test Files

| File | Action | Responsibility |
|------|--------|----------------|
| `trading/tests/unit/test_storage/test_memory_dedup.py` | Create | Dedup + WAL tests |
| `trading/tests/unit/test_storage/test_knowledge_graph.py` | Create | KG CRUD + temporal tests |
| `trading/tests/unit/test_learning/test_agent_context.py` | Create | L0/L1 generation + debounce tests |
| `.claude/knowledge/tests/test_flush_filter.py` | Create | Pre-filter unit tests |

---

## Sprint 1

### Task 1: Content-Hash Dedup + WAL in LocalMemoryStore

**Files:**
- Modify: `trading/storage/memory.py:56-99` (connect + _init_tables) and `:107-169` (store)
- Create: `trading/tests/unit/test_storage/test_memory_dedup.py`

- [ ] **Step 1: Write failing tests for dedup + WAL**

Create `trading/tests/unit/test_storage/test_memory_dedup.py`:

```python
"""Tests for content-hash dedup and WAL journaling in LocalMemoryStore."""

from __future__ import annotations

import asyncio

import aiosqlite
import pytest

from storage.memory import LocalMemoryStore


@pytest.fixture
async def store(tmp_path):
    s = LocalMemoryStore(db_path=str(tmp_path / "test.db"))
    await s.connect()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_wal_mode_enabled(store: LocalMemoryStore):
    cursor = await store._db.execute("PRAGMA journal_mode")
    row = await cursor.fetchone()
    assert row[0] == "wal"


@pytest.mark.asyncio
async def test_busy_timeout_set(store: LocalMemoryStore):
    cursor = await store._db.execute("PRAGMA busy_timeout")
    row = await cursor.fetchone()
    assert row[0] == 5000


@pytest.mark.asyncio
async def test_store_adds_content_hash(store: LocalMemoryStore):
    result = await store.store(value="test memory content")
    cursor = await store._db.execute(
        "SELECT content_hash FROM memories WHERE id = ?", (result["id"],)
    )
    row = await cursor.fetchone()
    assert row[0] is not None
    assert len(row[0]) == 32  # Full MD5 hex digest


@pytest.mark.asyncio
async def test_duplicate_store_returns_existing(store: LocalMemoryStore):
    first = await store.store(value="identical content")
    second = await store.store(value="identical content")
    assert second["id"] == first["id"]
    assert second["deduplicated"] is True


@pytest.mark.asyncio
async def test_duplicate_increments_access_count(store: LocalMemoryStore):
    first = await store.store(value="repeated lesson")
    await store.store(value="repeated lesson")
    await store.store(value="repeated lesson")
    record = await store.get(first["id"])
    assert record.access_count == 2  # Two dedup hits


@pytest.mark.asyncio
async def test_different_content_not_deduplicated(store: LocalMemoryStore):
    first = await store.store(value="content A")
    second = await store.store(value="content B")
    assert first["id"] != second["id"]
    assert second.get("deduplicated") is not True


@pytest.mark.asyncio
async def test_check_duplicate_finds_existing(store: LocalMemoryStore):
    await store.store(value="find me later")
    result = await store.check_duplicate("find me later")
    assert result is not None
    assert result.value == "find me later"


@pytest.mark.asyncio
async def test_check_duplicate_returns_none_for_new(store: LocalMemoryStore):
    result = await store.check_duplicate("never stored this")
    assert result is None


@pytest.mark.asyncio
async def test_concurrent_duplicate_stores(store: LocalMemoryStore):
    """Two concurrent stores of the same content: one INSERT, one UPDATE, no crash."""
    results = await asyncio.gather(
        store.store(value="concurrent content"),
        store.store(value="concurrent content"),
    )
    ids = {r["id"] for r in results}
    assert len(ids) == 1  # Same ID returned by both

    cursor = await store._db.execute("SELECT COUNT(*) FROM memories WHERE value = 'concurrent content'")
    row = await cursor.fetchone()
    assert row[0] == 1  # Only one row in DB
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_storage/test_memory_dedup.py -v --tb=short --timeout=30`

Expected: Multiple FAIL/ERROR (no `content_hash` column, no `check_duplicate` method, no WAL mode).

- [ ] **Step 3: Add WAL + busy_timeout to connect()**

Edit `trading/storage/memory.py`. After line 59 (`self._db.row_factory = aiosqlite.Row`), add:

```python
    async def connect(self) -> None:
        """Initialize the database connection and create tables."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._init_tables()
        logger.info("LocalMemoryStore connected to %s", self._db_path)
```

- [ ] **Step 4: Add content_hash column to schema**

Edit `trading/storage/memory.py` `_init_tables()`. After the existing `CREATE TABLE` and indexes (line 68-93), add the migration and new index:

```python
    async def _init_tables(self) -> None:
        """Create tables and indexes if they don't exist."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                agent_id TEXT,
                key TEXT,
                value TEXT NOT NULL,
                summary TEXT,
                memory_type TEXT,
                category TEXT,
                embedding BLOB,
                visibility TEXT DEFAULT 'private',
                importance INTEGER DEFAULT 5,
                confidence REAL DEFAULT 0.5,
                metadata TEXT DEFAULT '{}',
                tags TEXT DEFAULT '[]',
                access_count INTEGER DEFAULT 0,
                useful_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                content_hash TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
            CREATE INDEX IF NOT EXISTS idx_memories_visibility ON memories(visibility);
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash);
        """)

        -- Idempotent migration for existing databases
        try:
            await self._db.execute("ALTER TABLE memories ADD COLUMN content_hash TEXT")
            await self._db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash)"
            )
        except Exception:
            pass  # Column already exists

        await self._db.commit()
```

Wait — that uses SQL comment syntax in Python. Fix: the migration block should be pure Python:

```python
    async def _init_tables(self) -> None:
        """Create tables and indexes if they don't exist."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                agent_id TEXT,
                key TEXT,
                value TEXT NOT NULL,
                summary TEXT,
                memory_type TEXT,
                category TEXT,
                embedding BLOB,
                visibility TEXT DEFAULT 'private',
                importance INTEGER DEFAULT 5,
                confidence REAL DEFAULT 0.5,
                metadata TEXT DEFAULT '{}',
                tags TEXT DEFAULT '[]',
                access_count INTEGER DEFAULT 0,
                useful_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                content_hash TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
            CREATE INDEX IF NOT EXISTS idx_memories_visibility ON memories(visibility);
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash);
        """)

        # Idempotent migration: add content_hash to pre-existing databases
        try:
            await self._db.execute("ALTER TABLE memories ADD COLUMN content_hash TEXT")
            await self._db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash)"
            )
        except Exception:
            pass  # Column already exists

        await self._db.commit()
```

- [ ] **Step 5: Add hashlib import and modify store() for dedup**

Add `import hashlib` to the imports at the top of `trading/storage/memory.py` (after line 11, `from typing import Any, List`).

Replace the `store()` method (lines 107-169) with:

```python
    async def store(
        self,
        value: str,
        visibility: str = "private",
        agent_id: str | None = None,
        key: str | None = None,
        memory_type: str | None = None,
        category: str | None = None,
        embedding: List[float] | None = None,
        summary: str | None = None,
        tags: List[str] | None = None,
        metadata: dict | None = None,
        importance: int = 5,
        confidence: float = 0.5,
        ttl: str | None = None,
    ) -> dict:
        """Store a memory. Deduplicates by content hash — returns existing record if identical."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        content_hash = hashlib.md5(value.encode()).hexdigest()
        now = datetime.now(timezone.utc)

        # Check for existing memory with same content
        cursor = await self._db.execute(
            "SELECT id, access_count FROM memories WHERE content_hash = ?",
            (content_hash,),
        )
        existing = await cursor.fetchone()
        if existing:
            await self._db.execute(
                "UPDATE memories SET access_count = access_count + 1, updated_at = ? WHERE id = ?",
                (now.isoformat(), existing["id"]),
            )
            await self._db.commit()
            return {
                "id": existing["id"],
                "key": key,
                "value": value,
                "visibility": visibility,
                "created_at": now.isoformat(),
                "deduplicated": True,
            }

        memory_id = str(uuid.uuid4())
        expires_at = None
        if ttl:
            pass  # Parse TTL like "90d" - store without expiry for now

        await self._db.execute(
            """
            INSERT INTO memories (
                id, agent_id, key, value, summary, memory_type, category,
                embedding, visibility, importance, confidence, metadata, tags,
                created_at, updated_at, expires_at, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                agent_id,
                key,
                value,
                summary,
                memory_type,
                category,
                json.dumps(embedding) if embedding else None,
                visibility,
                importance,
                confidence,
                json.dumps(metadata or {}),
                json.dumps(tags or []),
                now.isoformat(),
                now.isoformat(),
                expires_at.isoformat() if expires_at else None,
                content_hash,
            ),
        )
        await self._db.commit()

        return {
            "id": memory_id,
            "key": key,
            "value": value,
            "visibility": visibility,
            "created_at": now.isoformat(),
        }
```

- [ ] **Step 6: Add check_duplicate() method**

Add after the `store()` method (before `get()`):

```python
    async def check_duplicate(self, value: str) -> MemoryRecord | None:
        """Check if a memory with identical content already exists."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        content_hash = hashlib.md5(value.encode()).hexdigest()
        cursor = await self._db.execute(
            "SELECT * FROM memories WHERE content_hash = ?", (content_hash,)
        )
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_storage/test_memory_dedup.py -v --tb=short --timeout=30`

Expected: All 9 tests PASS.

- [ ] **Step 8: Run existing tests to verify no regressions**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_storage/ -v --tb=short --timeout=30`

Expected: All existing storage tests still pass.

- [ ] **Step 9: Commit**

```bash
cd /opt/agent-memory-unified
git add trading/storage/memory.py trading/tests/unit/test_storage/test_memory_dedup.py
git commit -m "feat(memory): add content-hash dedup and WAL journaling to LocalMemoryStore

- MD5 content hash with UNIQUE index prevents duplicate memories
- Duplicate stores increment access_count and update updated_at
- PRAGMA journal_mode=WAL + busy_timeout=5000 for concurrent safety
- New check_duplicate() method for explicit duplicate detection"
```

---

### Task 2: WAL Journaling on DatabaseConnection

**Files:**
- Modify: `trading/storage/db.py:52-56`

- [ ] **Step 1: Add WAL + busy_timeout to SQLite branch of DatabaseConnection.connect()**

Edit `trading/storage/db.py`. After line 54 (`self.connection.row_factory = aiosqlite.Row`), add the pragmas:

```python
        # SQLite mode
        self.connection = await aiosqlite.connect(self.config.db_path or "data.db")
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA journal_mode=WAL")
        await self.connection.execute("PRAGMA busy_timeout=5000")
        await init_db(self.connection)
        return self.connection
```

- [ ] **Step 2: Run existing DB tests to verify no regressions**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_storage/test_db.py tests/storage/ -v --tb=short --timeout=30`

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
cd /opt/agent-memory-unified
git add trading/storage/db.py
git commit -m "feat(storage): add WAL journaling + busy_timeout to DatabaseConnection

Prevents 'database is locked' errors under concurrent agent reads/writes."
```

---

### Task 3: Pattern Pre-Filter in flush.py

**Files:**
- Modify: `.claude/knowledge/scripts/flush.py:216-226`
- Create: `.claude/knowledge/tests/test_flush_filter.py`

- [ ] **Step 1: Write failing tests for the pre-filter**

Create `.claude/knowledge/tests/test_flush_filter.py`:

```python
"""Tests for the knowledge signal pre-filter in flush.py."""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts dir to path so we can import flush module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from flush import has_knowledge_signal


def test_noise_only_context_returns_false():
    context = """**Read** /opt/agent-memory-unified/trading/config.py
**Bash** git status
**User**: yes
**Assistant**: Done.
**Glob** *.py"""
    assert has_knowledge_signal(context) is False


def test_empty_context_returns_false():
    assert has_knowledge_signal("") is False


def test_decision_markers_return_true():
    context = """**User**: I decided to switch to WAL mode for the database config.
**Assistant**: Good choice. WAL mode provides better concurrent read performance."""
    assert has_knowledge_signal(context) is True


def test_problem_and_fix_returns_true():
    context = """**User**: There's a bug in the bridge polling — it crashed overnight.
**Assistant**: The root cause was a stale file handle. Here's the fix."""
    assert has_knowledge_signal(context) is True


def test_silent_refactor_triggers_on_writes():
    context = """**Write** trading/storage/knowledge_graph.py
**Edit** trading/agents/base.py
**Read** trading/config.py
**Edit** trading/api/app.py"""
    assert has_knowledge_signal(context) is True  # 1 Write >= threshold


def test_many_edits_triggers():
    context = """**Edit** file1.py
**Edit** file2.py
**Edit** file3.py
**Edit** file4.py"""
    assert has_knowledge_signal(context) is True  # 4 Edits > 3


def test_user_hint_always_triggers():
    context = """**Read** some_file.py
User hint: remember this config change for next time"""
    assert has_knowledge_signal(context) is True


def test_remember_this_always_triggers():
    context = """**Bash** git log
remember this deployment procedure"""
    assert has_knowledge_signal(context) is True


def test_single_marker_not_enough():
    """A single keyword match like 'error' in tool output shouldn't trigger."""
    context = """**Bash** python -m pytest
FAILED: 1 error in test_something.py
**User**: ok
**Assistant**: Let me look at that."""
    assert has_knowledge_signal(context) is False


def test_ansi_codes_stripped():
    context = """\x1b[31mERROR\x1b[0m something failed
**User**: yes
**Assistant**: ok"""
    assert has_knowledge_signal(context) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/agent-memory-unified && python -m pytest .claude/knowledge/tests/test_flush_filter.py -v --tb=short --timeout=30`

Expected: FAIL — `has_knowledge_signal` not defined in flush module.

- [ ] **Step 3: Add has_knowledge_signal() to flush.py**

Edit `.claude/knowledge/scripts/flush.py`. Add the following after the imports block (after line 28, before `DAILY_DIR`):

```python
import re

# Pattern pre-filter: skip LLM call if context has no knowledge-bearing signals.
# Keyword lists adapted from MemPalace general_extractor.py.
_DECISION_MARKERS = [
    "decided", "let's use", "go with", "switched to", "trade-off",
    "chose", "architecture", "we went with", "settled on", "approach",
]
_PROBLEM_MARKERS = [
    "bug", "broke", "error", "root cause", "fix", "workaround",
    "crashed", "doesn't work", "issue", "regression",
]
_MILESTONE_MARKERS = [
    "it works", "shipped", "deployed", "figured out", "breakthrough",
    "fixed", "solved", "nailed it", "released",
]
_LESSON_MARKERS = [
    "learned", "gotcha", "turns out", "important to note", "the trick is",
    "key insight", "remember that", "lesson",
]
_CONFIG_MARKERS = [
    "env var", "config", "setting", "enabled", "disabled", "toggled",
    "migration", "schema change",
]
_ALL_MARKERS = (
    _DECISION_MARKERS + _PROBLEM_MARKERS + _MILESTONE_MARKERS
    + _LESSON_MARKERS + _CONFIG_MARKERS
)

_NOISE_PATTERNS = [
    re.compile(r"^\*\*(Read|Glob|Bash|Grep)\*\*"),
    re.compile(r"^\[File contents?\]"),
    re.compile(r"^\*\*(User|Assistant)\*\*:\s*(yes|no|y|n|ok|okay|continue|next|thanks?)\s*$", re.I),
    re.compile(r"\x1b\[[0-9;]*m"),
]


def has_knowledge_signal(context: str) -> bool:
    """Return True if context contains patterns worth an LLM extraction call."""
    if not context.strip():
        return False

    lines = context.splitlines()
    clean_lines = [l for l in lines if not any(p.search(l) for p in _NOISE_PATTERNS)]
    clean_text = "\n".join(clean_lines).lower()

    # Explicit user hints always trigger
    if "user hint:" in clean_text or "remember this" in clean_text:
        return True

    # Silent refactor: any new file creation or heavy editing
    write_count = sum(1 for l in lines if re.match(r"^\*\*Write\*\*", l))
    edit_count = sum(1 for l in lines if re.match(r"^\*\*Edit\*\*", l))
    if write_count >= 1 or edit_count > 3:
        return True

    # Check knowledge marker lists — require 2+ hits to avoid false positives
    matches = sum(1 for m in _ALL_MARKERS if m in clean_text)
    return matches >= 2
```

- [ ] **Step 4: Wire the pre-filter into main()**

Edit `.claude/knowledge/scripts/flush.py`. In the `main()` function, after reading the context (line 217: `context = context_file.read_text(...)`) and before the LLM call (line 226: `response = asyncio.run(run_flush(context))`), add the pre-filter check:

```python
    # Read pre-extracted context
    context = context_file.read_text(encoding="utf-8").strip()
    if not context:
        logging.info("Context file is empty, skipping")
        context_file.unlink(missing_ok=True)
        return

    # Pre-filter: skip LLM call if context has no knowledge signals
    if not has_knowledge_signal(context):
        logging.info(
            "Skipping flush: no knowledge signals in %d-char context", len(context)
        )
        context_file.unlink(missing_ok=True)
        save_flush_state({"session_id": session_id, "timestamp": time.time()})
        return

    logging.info("Flushing session %s: %d chars", session_id, len(context))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /opt/agent-memory-unified && python -m pytest .claude/knowledge/tests/test_flush_filter.py -v --tb=short --timeout=30`

Expected: All 10 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /opt/agent-memory-unified
git add .claude/knowledge/scripts/flush.py .claude/knowledge/tests/test_flush_filter.py
git commit -m "feat(knowledge): add pattern pre-filter to flush.py

Skips LLM extraction call when context has no decision/problem/milestone/lesson
markers. Expected ~30-40% reduction in flush API costs.

Keyword lists adapted from MemPalace general_extractor.py."
```

---

## Sprint 2

### Task 4: Temporal Knowledge Graph

**Files:**
- Create: `trading/storage/knowledge_graph.py`
- Create: `trading/tests/unit/test_storage/test_knowledge_graph.py`

- [ ] **Step 1: Write failing tests for the KG**

Create `trading/tests/unit/test_storage/test_knowledge_graph.py`:

```python
"""Tests for the temporal knowledge graph."""

from __future__ import annotations

import pytest

from storage.knowledge_graph import TradingKnowledgeGraph


@pytest.fixture
async def kg(tmp_path):
    g = TradingKnowledgeGraph(db_path=str(tmp_path / "kg.db"))
    await g.connect()
    yield g
    await g.close()


@pytest.mark.asyncio
async def test_add_and_query_entity(kg: TradingKnowledgeGraph):
    await kg.add_triple("btc_regime", "in_state", "bull", valid_from="2026-01-01", source="test")
    facts = await kg.query_entity("btc_regime")
    assert len(facts) == 1
    assert facts[0]["predicate"] == "in_state"
    assert facts[0]["object"] == "bull"


@pytest.mark.asyncio
async def test_temporal_filter_excludes_expired(kg: TradingKnowledgeGraph):
    await kg.add_triple("btc_regime", "in_state", "bear",
                        valid_from="2025-01-01", valid_to="2025-12-31", source="test")
    await kg.add_triple("btc_regime", "in_state", "bull",
                        valid_from="2026-01-01", source="test")

    # Query as of mid-2025: should see bear only
    facts_2025 = await kg.query_entity("btc_regime", as_of="2025-06-15")
    assert len(facts_2025) == 1
    assert facts_2025[0]["object"] == "bear"

    # Query as of 2026: should see bull only
    facts_2026 = await kg.query_entity("btc_regime", as_of="2026-03-01")
    assert len(facts_2026) == 1
    assert facts_2026[0]["object"] == "bull"


@pytest.mark.asyncio
async def test_invalidate_sets_valid_to_and_reason(kg: TradingKnowledgeGraph):
    await kg.add_triple("miner_abc", "active_on", "subnet8",
                        valid_from="2026-01-01", source="bridge")
    await kg.invalidate("miner_abc", "active_on", "subnet8",
                        ended="2026-03-15", reason="high_latency")

    # Should be expired now
    facts = await kg.query_entity("miner_abc", as_of="2026-04-01")
    assert len(facts) == 0

    # Timeline should show the reason
    tl = await kg.timeline("miner_abc")
    assert len(tl) == 1
    assert tl[0]["invalidation_reason"] == "high_latency"
    assert tl[0]["valid_to"] == "2026-03-15"


@pytest.mark.asyncio
async def test_timeline_ordered_by_valid_from(kg: TradingKnowledgeGraph):
    await kg.add_triple("btc_regime", "in_state", "bear",
                        valid_from="2025-01-01", valid_to="2025-12-31", source="test")
    await kg.add_triple("btc_regime", "in_state", "bull",
                        valid_from="2026-01-01", source="test")
    await kg.add_triple("btc_regime", "volatility", "high",
                        valid_from="2025-06-01", valid_to="2025-09-01", source="test")

    tl = await kg.timeline("btc_regime")
    dates = [t["valid_from"] for t in tl]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_query_relationship(kg: TradingKnowledgeGraph):
    await kg.add_triple("miner_a", "active_on", "subnet8", valid_from="2026-01-01", source="bridge")
    await kg.add_triple("miner_b", "active_on", "subnet8", valid_from="2026-02-01", source="bridge")
    await kg.add_triple("miner_a", "alpha_on", "BTCUSD", valid_from="2026-01-01", source="evaluator")

    active = await kg.query_relationship("active_on")
    assert len(active) == 2


@pytest.mark.asyncio
async def test_stats(kg: TradingKnowledgeGraph):
    await kg.add_triple("btc_regime", "in_state", "bull", valid_from="2026-01-01", source="test")
    await kg.add_triple("miner_a", "active_on", "subnet8", valid_from="2026-01-01", source="bridge")
    await kg.invalidate("miner_a", "active_on", "subnet8", ended="2026-03-01", reason="offline")

    s = await kg.stats()
    assert s["entities"] >= 3  # btc_regime, miner_a, bull, subnet8
    assert s["triples"] == 2
    assert s["expired_facts"] == 1
    assert s["current_facts"] == 1


@pytest.mark.asyncio
async def test_add_triple_with_properties(kg: TradingKnowledgeGraph):
    triple_id = await kg.add_triple(
        "miner_uid_144", "weight_set_to", "0.045",
        valid_from="2026-04-08", source="weight_setter",
        properties={"alpha": 0.3, "beta": 0.7},
    )
    facts = await kg.query_entity("miner_uid_144")
    assert len(facts) == 1
    assert facts[0]["properties"]["alpha"] == 0.3


@pytest.mark.asyncio
async def test_duplicate_triple_not_inserted(kg: TradingKnowledgeGraph):
    id1 = await kg.add_triple("x", "rel", "y", valid_from="2026-01-01", source="test")
    id2 = await kg.add_triple("x", "rel", "y", valid_from="2026-01-01", source="test")
    assert id1 == id2
    s = await kg.stats()
    assert s["triples"] == 1


@pytest.mark.asyncio
async def test_bidirectional_query(kg: TradingKnowledgeGraph):
    await kg.add_triple("miner_a", "signal_on", "BTCUSD", valid_from="2026-01-01", source="bridge")
    # Query BTCUSD incoming
    facts = await kg.query_entity("BTCUSD", direction="incoming")
    assert len(facts) == 1
    assert facts[0]["subject"] == "miner_a"
    # Query both directions
    facts_both = await kg.query_entity("miner_a", direction="both")
    assert len(facts_both) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_storage/test_knowledge_graph.py -v --tb=short --timeout=30`

Expected: FAIL — module `storage.knowledge_graph` does not exist.

- [ ] **Step 3: Implement TradingKnowledgeGraph**

Create `trading/storage/knowledge_graph.py`:

```python
"""Temporal knowledge graph for trading domain facts.

Stores entity-relationship triples with temporal validity windows.
Ported from MemPalace knowledge_graph.py, adapted for async + trading domain.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT DEFAULT 'unknown',
    properties TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS kg_triples (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    confidence REAL DEFAULT 1.0,
    source TEXT,
    properties TEXT DEFAULT '{}',
    invalidation_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject) REFERENCES kg_entities(id),
    FOREIGN KEY (object) REFERENCES kg_entities(id)
);

CREATE INDEX IF NOT EXISTS idx_kg_triples_subject ON kg_triples(subject);
CREATE INDEX IF NOT EXISTS idx_kg_triples_object ON kg_triples(object);
CREATE INDEX IF NOT EXISTS idx_kg_triples_predicate ON kg_triples(predicate);
CREATE INDEX IF NOT EXISTS idx_kg_triples_valid ON kg_triples(valid_from, valid_to);
"""


class TradingKnowledgeGraph:
    """Temporal entity-relationship graph stored in SQLite."""

    def __init__(self, db_path: str = "data/knowledge_graph.sqlite3") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("TradingKnowledgeGraph connected to %s", self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @staticmethod
    def _entity_id(name: str) -> str:
        """Normalize name to entity ID: lowercase, spaces to underscores."""
        return name.lower().replace(" ", "_").replace("'", "")

    async def add_entity(
        self, name: str, entity_type: str = "unknown", properties: dict | None = None,
    ) -> str:
        eid = self._entity_id(name)
        await self._db.execute(
            """INSERT INTO kg_entities (id, name, entity_type, properties)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 entity_type = COALESCE(NULLIF(excluded.entity_type, 'unknown'), entity_type),
                 properties = excluded.properties""",
            (eid, name, entity_type, json.dumps(properties or {})),
        )
        await self._db.commit()
        return eid

    async def add_triple(
        self,
        subject: str,
        predicate: str,
        obj: str,
        valid_from: str | None = None,
        valid_to: str | None = None,
        confidence: float = 1.0,
        source: str | None = None,
        properties: dict | None = None,
    ) -> str:
        sub_id = self._entity_id(subject)
        obj_id = self._entity_id(obj)

        # Auto-create entities
        await self.add_entity(subject)
        await self.add_entity(obj)

        # Deterministic triple ID
        raw = f"{sub_id}_{predicate}_{obj_id}_{valid_from or ''}"
        h = hashlib.md5(raw.encode()).hexdigest()[:8]
        triple_id = f"t_{sub_id}_{predicate}_{obj_id}_{h}"

        # Check for existing identical triple
        cursor = await self._db.execute("SELECT id FROM kg_triples WHERE id = ?", (triple_id,))
        if await cursor.fetchone():
            return triple_id  # Already exists

        await self._db.execute(
            """INSERT INTO kg_triples
               (id, subject, predicate, object, valid_from, valid_to, confidence, source, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (triple_id, sub_id, predicate, obj_id, valid_from, valid_to,
             confidence, source, json.dumps(properties or {})),
        )
        await self._db.commit()
        return triple_id

    async def invalidate(
        self,
        subject: str,
        predicate: str,
        obj: str,
        ended: str | None = None,
        reason: str | None = None,
    ) -> None:
        sub_id = self._entity_id(subject)
        obj_id = self._entity_id(obj)
        end_date = ended or date.today().isoformat()

        await self._db.execute(
            """UPDATE kg_triples
               SET valid_to = ?, invalidation_reason = ?
               WHERE subject = ? AND predicate = ? AND object = ? AND valid_to IS NULL""",
            (end_date, reason, sub_id, predicate, obj_id),
        )
        await self._db.commit()

    async def query_entity(
        self,
        name: str,
        as_of: str | None = None,
        direction: str = "outgoing",
    ) -> list[dict]:
        eid = self._entity_id(name)
        results = []

        if direction in ("outgoing", "both"):
            sql = "SELECT * FROM kg_triples WHERE subject = ?"
            params: list = [eid]
            if as_of:
                sql += " AND (valid_from IS NULL OR valid_from <= ?)"
                sql += " AND (valid_to IS NULL OR valid_to >= ?)"
                params.extend([as_of, as_of])
            cursor = await self._db.execute(sql, params)
            for row in await cursor.fetchall():
                results.append(self._triple_to_dict(row))

        if direction in ("incoming", "both"):
            sql = "SELECT * FROM kg_triples WHERE object = ?"
            params = [eid]
            if as_of:
                sql += " AND (valid_from IS NULL OR valid_from <= ?)"
                sql += " AND (valid_to IS NULL OR valid_to >= ?)"
                params.extend([as_of, as_of])
            cursor = await self._db.execute(sql, params)
            for row in await cursor.fetchall():
                results.append(self._triple_to_dict(row))

        return results

    async def query_relationship(
        self, predicate: str, as_of: str | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM kg_triples WHERE predicate = ?"
        params: list = [predicate]
        if as_of:
            sql += " AND (valid_from IS NULL OR valid_from <= ?)"
            sql += " AND (valid_to IS NULL OR valid_to >= ?)"
            params.extend([as_of, as_of])
        cursor = await self._db.execute(sql, params)
        return [self._triple_to_dict(row) for row in await cursor.fetchall()]

    async def timeline(
        self, entity_name: str | None = None, limit: int = 100,
    ) -> list[dict]:
        if entity_name:
            eid = self._entity_id(entity_name)
            sql = """SELECT * FROM kg_triples
                     WHERE subject = ? OR object = ?
                     ORDER BY COALESCE(valid_from, '0000') ASC LIMIT ?"""
            params: list = [eid, eid, limit]
        else:
            sql = """SELECT * FROM kg_triples
                     ORDER BY COALESCE(valid_from, '0000') ASC LIMIT ?"""
            params = [limit]
        cursor = await self._db.execute(sql, params)
        return [self._triple_to_dict(row) for row in await cursor.fetchall()]

    async def stats(self) -> dict:
        cursor = await self._db.execute("SELECT COUNT(*) FROM kg_entities")
        entities = (await cursor.fetchone())[0]
        cursor = await self._db.execute("SELECT COUNT(*) FROM kg_triples")
        triples = (await cursor.fetchone())[0]
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM kg_triples WHERE valid_to IS NOT NULL"
        )
        expired = (await cursor.fetchone())[0]
        cursor = await self._db.execute(
            "SELECT COUNT(DISTINCT predicate) FROM kg_triples"
        )
        rel_types = (await cursor.fetchone())[0]
        return {
            "entities": entities,
            "triples": triples,
            "current_facts": triples - expired,
            "expired_facts": expired,
            "relationship_types": rel_types,
        }

    @staticmethod
    def _triple_to_dict(row: aiosqlite.Row) -> dict:
        return {
            "id": row["id"],
            "subject": row["subject"],
            "predicate": row["predicate"],
            "object": row["object"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "confidence": row["confidence"],
            "source": row["source"],
            "properties": json.loads(row["properties"]) if row["properties"] else {},
            "invalidation_reason": row["invalidation_reason"],
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_storage/test_knowledge_graph.py -v --tb=short --timeout=30`

Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /opt/agent-memory-unified
git add trading/storage/knowledge_graph.py trading/tests/unit/test_storage/test_knowledge_graph.py
git commit -m "feat(storage): add temporal knowledge graph for trading domain

SQLite-based entity-relationship triples with temporal validity windows.
Supports add/invalidate/query/timeline with as_of filtering.
Ported from MemPalace knowledge_graph.py, adapted for async + trading."
```

---

### Task 5: Layered Agent Context (L0 + L1) in PromptStore

**Files:**
- Modify: `trading/learning/prompt_store.py`
- Create: `trading/tests/unit/test_learning/test_agent_context.py`

- [ ] **Step 1: Write failing tests for agent context generation**

Create `trading/tests/unit/test_learning/test_agent_context.py`:

```python
"""Tests for L0/L1 layered agent context in SqlPromptStore."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from learning.prompt_store import SqlPromptStore


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS llm_prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            rules TEXT NOT NULL,
            performance_at_creation TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS llm_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            opportunity_id TEXT NOT NULL,
            category TEXT NOT NULL,
            lesson TEXT NOT NULL,
            applies_to TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            archived_at TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_context_cache (
            agent_name TEXT PRIMARY KEY,
            l0_text TEXT NOT NULL,
            l1_text TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            trade_count INTEGER DEFAULT 0
        );
    """)
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
async def store(db):
    return SqlPromptStore(db)


def _make_agent_config(name="rsi_scanner", strategy="RSI momentum",
                       action_level="suggest_trade", universe=None,
                       schedule="continuous", description="Test agent"):
    cfg = MagicMock()
    cfg.name = name
    cfg.strategy = strategy
    cfg.action_level = action_level
    cfg.universe = universe or ["AAPL", "MSFT"]
    cfg.schedule = schedule
    cfg.description = description
    cfg.trust_level = "monitored"
    cfg.interval = 60
    return cfg


@pytest.mark.asyncio
async def test_l0_generated_from_config(store: SqlPromptStore):
    config = _make_agent_config()
    await store.generate_agent_context(agent_name="rsi_scanner", agent_config=config)
    ctx = store.get_agent_context("rsi_scanner")
    assert ctx is not None
    assert "rsi_scanner" in ctx
    assert "RSI momentum" in ctx
    assert "suggest_trade" in ctx


@pytest.mark.asyncio
async def test_l1_empty_state_for_new_agent(store: SqlPromptStore):
    config = _make_agent_config()
    await store.generate_agent_context(agent_name="rsi_scanner", agent_config=config)
    ctx = store.get_agent_context("rsi_scanner")
    assert "No historical trades" in ctx or "no historical" in ctx.lower()


@pytest.mark.asyncio
async def test_l1_with_trade_memories(store: SqlPromptStore):
    config = _make_agent_config()
    memories = [
        {"value": "AAPL +$340 win strong RSI divergence", "importance": 9},
        {"value": "MSFT -$180 loss false breakout", "importance": 8},
        {"value": "GOOGL +$95 win clean momentum", "importance": 7},
    ]
    await store.generate_agent_context(
        agent_name="rsi_scanner", agent_config=config, trade_memories=memories,
    )
    ctx = store.get_agent_context("rsi_scanner")
    assert "AAPL" in ctx
    assert "MSFT" in ctx


@pytest.mark.asyncio
async def test_debounce_prevents_regeneration(store: SqlPromptStore):
    config = _make_agent_config()
    await store.generate_agent_context(agent_name="rsi_scanner", agent_config=config)
    first_ctx = store.get_agent_context("rsi_scanner")

    # Attempt regeneration immediately — should be skipped
    regenerated = await store.maybe_regenerate_context(
        agent_name="rsi_scanner", agent_config=config, min_interval_minutes=30,
    )
    assert regenerated is False
    assert store.get_agent_context("rsi_scanner") == first_ctx


@pytest.mark.asyncio
async def test_get_agent_context_returns_none_when_empty(store: SqlPromptStore):
    ctx = store.get_agent_context("nonexistent_agent")
    assert ctx is None


@pytest.mark.asyncio
async def test_context_cached_in_db(store: SqlPromptStore):
    config = _make_agent_config()
    await store.generate_agent_context(agent_name="rsi_scanner", agent_config=config)

    cursor = await store._db.execute(
        "SELECT * FROM agent_context_cache WHERE agent_name = ?", ("rsi_scanner",)
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row["agent_name"] == "rsi_scanner"
    assert row["l0_text"] != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_learning/test_agent_context.py -v --tb=short --timeout=30`

Expected: FAIL — `generate_agent_context`, `get_agent_context`, `maybe_regenerate_context` not defined.

- [ ] **Step 3: Add agent_context_cache table creation to SqlPromptStore**

Edit `trading/learning/prompt_store.py`. The table is created externally (in `app.py` or test fixtures), but we need to add the methods. First, add the `datetime` import at the top:

```python
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import aiosqlite
```

- [ ] **Step 4: Add generate_agent_context(), get_agent_context(), maybe_regenerate_context()**

Add these methods to `SqlPromptStore` after the `get_version_history` method (after line 139):

```python
    # --- L0/L1 Layered Agent Context ---

    _context_cache: dict[str, str] = {}

    def get_agent_context(self, agent_name: str) -> str | None:
        """Return cached L0+L1 context string, or None if not generated."""
        ctx = self._context_cache.get(agent_name)
        return ctx if ctx else None

    async def generate_agent_context(
        self,
        agent_name: str,
        agent_config: Any,
        trade_memories: list[dict] | None = None,
        regime_context: str | None = None,
    ) -> None:
        """Generate L0 (identity) + L1 (performance story) and cache."""
        # L0: Agent Identity
        universe = agent_config.universe
        if isinstance(universe, list):
            universe = ", ".join(universe[:6])
            if len(agent_config.universe) > 6:
                universe += f" (+{len(agent_config.universe) - 6} more)"
        l0 = (
            f"## Identity\n"
            f"Agent: {agent_name} | Strategy: {agent_config.strategy} "
            f"| Action: {agent_config.action_level}\n"
            f"Universe: {universe} | Schedule: {agent_config.schedule}"
        )
        if hasattr(agent_config, "description") and agent_config.description:
            l0 += f"\n{agent_config.description}"

        # L1: Performance Story
        if not trade_memories:
            l1 = (
                "## Recent Performance\n"
                "New agent — no historical trades recorded yet. "
                "Operating without performance context."
            )
        else:
            sorted_mems = sorted(trade_memories, key=lambda m: m.get("importance", 0), reverse=True)
            top = sorted_mems[:10]
            lines = ["## Recent Performance"]
            if regime_context:
                lines.append(f"Regime: {regime_context}")
            lines.append("")
            for mem in top:
                lines.append(f"- {mem['value'][:200]}")
            l1 = "\n".join(lines)

        combined = f"{l0}\n\n{l1}"
        self._context_cache[agent_name] = combined

        # Persist to DB
        now_iso = datetime.now(timezone.utc).isoformat()
        trade_count = len(trade_memories) if trade_memories else 0
        await self._db.execute(
            """INSERT INTO agent_context_cache (agent_name, l0_text, l1_text, generated_at, trade_count)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(agent_name) DO UPDATE SET
                 l0_text = excluded.l0_text,
                 l1_text = excluded.l1_text,
                 generated_at = excluded.generated_at,
                 trade_count = excluded.trade_count""",
            (agent_name, l0, l1, now_iso, trade_count),
        )
        await self._db.commit()

    async def maybe_regenerate_context(
        self,
        agent_name: str,
        agent_config: Any,
        trade_memories: list[dict] | None = None,
        regime_context: str | None = None,
        min_interval_minutes: int = 30,
    ) -> bool:
        """Regenerate context if enough time has passed. Returns True if regenerated."""
        cursor = await self._db.execute(
            "SELECT generated_at FROM agent_context_cache WHERE agent_name = ?",
            (agent_name,),
        )
        row = await cursor.fetchone()
        if row:
            generated = datetime.fromisoformat(row["generated_at"])
            elapsed = (datetime.now(timezone.utc) - generated).total_seconds() / 60
            if elapsed < min_interval_minutes:
                return False

        await self.generate_agent_context(
            agent_name=agent_name,
            agent_config=agent_config,
            trade_memories=trade_memories,
            regime_context=regime_context,
        )
        return True
```

Also initialize `_context_cache` in `__init__`:

```python
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._prompts: dict[str, str] = {}
        self._context_cache: dict[str, str] = {}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_learning/test_agent_context.py -v --tb=short --timeout=30`

Expected: All 6 tests PASS.

- [ ] **Step 6: Run existing prompt_store tests to verify no regressions**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_learning/test_prompt_store.py -v --tb=short --timeout=30`

Expected: All existing tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /opt/agent-memory-unified
git add trading/learning/prompt_store.py trading/tests/unit/test_learning/test_agent_context.py
git commit -m "feat(learning): add L0/L1 layered agent context to SqlPromptStore

L0 (Identity): agent name, strategy, universe from config.
L1 (Performance): top trades by importance, regime-aware when available.
30-minute debounce prevents excessive regeneration.
Cached in agent_context_cache table + in-memory dict."
```

---

### Task 6: Wire L0+L1 into LLMAgent.system_prompt

**Files:**
- Modify: `trading/agents/base.py:76-82`

- [ ] **Step 1: Update LLMAgent.system_prompt to include agent context**

Edit `trading/agents/base.py`. Replace the `system_prompt` property (lines 76-82):

```python
    @property
    def system_prompt(self) -> str:
        base = self._config.system_prompt or ""
        context = ""
        if self._prompt_store:
            # L0 + L1 context (identity + performance story)
            agent_ctx = self._prompt_store.get_agent_context(self.name)
            if agent_ctx:
                context = agent_ctx
            # Learned rules from prompt versioning
            learned = self._prompt_store.get_runtime_prompt(self.name)
            if learned:
                context = f"{context}\n\n{learned}" if context else learned
        return f"{base}\n\n{context}" if context else base
```

- [ ] **Step 2: Run existing agent tests to verify no regressions**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_agents/ -v --tb=short --timeout=30`

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
cd /opt/agent-memory-unified
git add trading/agents/base.py
git commit -m "feat(agents): wire L0+L1 context into LLMAgent.system_prompt

System prompt now includes identity + performance story from PromptStore
before learned rules. Separates internal state (system_prompt) from
environment state (AgentRunner._execute_scan)."
```

---

### Task 7: Prime Agent Context on Startup

**Files:**
- Modify: `trading/agents/runner.py`

- [ ] **Step 1: Read the start_agent method to find the injection point**

Read `trading/agents/runner.py` and find the `start_agent` method. It should be around lines 70-120.

- [ ] **Step 2: Add context priming call in start_agent()**

In `AgentRunner.__init__`, add `self._prompt_store = None` and `self._knowledge_graph = None` fields. Add setter methods or constructor params as needed based on what `app.py` passes.

In `start_agent()`, before `await agent.setup()`, add:

```python
        # Prime L0+L1 context (no cold starts)
        if hasattr(agent, '_prompt_store') and agent._prompt_store:
            await agent._prompt_store.generate_agent_context(
                agent_name=name,
                agent_config=agent._config,
            )
```

This is minimal — it generates L0 from config with empty L1 (no trade memories yet at startup). As trades close and deep reflections trigger, L1 gets populated via `maybe_regenerate_context`.

- [ ] **Step 3: Run existing runner tests**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_agents/test_runner.py -v --tb=short --timeout=30`

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
cd /opt/agent-memory-unified
git add trading/agents/runner.py
git commit -m "feat(agents): prime L0+L1 context on agent startup

Calls generate_agent_context() before agent.setup() to ensure
LLM agents have identity context from first scan."
```

---

### Task 8: KG API Endpoints

**Files:**
- Modify: `trading/api/routes/bittensor.py`

- [ ] **Step 1: Read bittensor.py to find the router and existing patterns**

Read `trading/api/routes/bittensor.py` to understand existing route patterns, dependency injection, and response formats.

- [ ] **Step 2: Add three KG endpoints**

Add to the bittensor router:

```python
@router.get("/kg/entity/{name}")
async def kg_entity(
    name: str,
    as_of: str | None = None,
    direction: str = "both",
    request: Request = None,
):
    """Query knowledge graph for entity facts."""
    kg = request.app.state.knowledge_graph
    if not kg:
        return {"error": "Knowledge graph not initialized"}
    facts = await kg.query_entity(name, as_of=as_of, direction=direction)
    return {"entity": name, "facts": facts, "count": len(facts)}


@router.get("/kg/timeline")
async def kg_timeline(
    entity: str | None = None,
    limit: int = 50,
    request: Request = None,
):
    """Get chronological timeline of KG facts."""
    kg = request.app.state.knowledge_graph
    if not kg:
        return {"error": "Knowledge graph not initialized"}
    tl = await kg.timeline(entity_name=entity, limit=limit)
    return {"entity": entity, "timeline": tl, "count": len(tl)}


@router.get("/kg/stats")
async def kg_stats(request: Request):
    """Get knowledge graph statistics."""
    kg = request.app.state.knowledge_graph
    if not kg:
        return {"error": "Knowledge graph not initialized"}
    return await kg.stats()
```

- [ ] **Step 3: Run existing bittensor API tests**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_api/ -k bittensor -v --tb=short --timeout=30`

Expected: All existing tests still pass.

- [ ] **Step 4: Commit**

```bash
cd /opt/agent-memory-unified
git add trading/api/routes/bittensor.py
git commit -m "feat(api): add KG read endpoints for entity, timeline, and stats

GET /api/bittensor/kg/entity/{name}?as_of=...&direction=both
GET /api/bittensor/kg/timeline?entity=...&limit=50
GET /api/bittensor/kg/stats"
```

---

### Task 9: Final Integration — Run Full Test Suite

- [ ] **Step 1: Run all unit tests**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/ -v --tb=short --timeout=30 -x`

Expected: All pass. If any fail, fix before proceeding.

- [ ] **Step 2: Run all new tests specifically**

Run: `cd /opt/agent-memory-unified/trading && python -m pytest tests/unit/test_storage/test_memory_dedup.py tests/unit/test_storage/test_knowledge_graph.py tests/unit/test_learning/test_agent_context.py -v --tb=short --timeout=30`

And: `cd /opt/agent-memory-unified && python -m pytest .claude/knowledge/tests/test_flush_filter.py -v --tb=short --timeout=30`

Expected: All 25+ new tests pass.

- [ ] **Step 3: Final commit with all changes verified**

If any uncommitted fixes were needed, commit them now with a descriptive message.
