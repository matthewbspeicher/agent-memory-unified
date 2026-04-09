"""Local Memory Store with pgvector for hybrid memory architecture.

Provides local fallback when remembr.dev is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List

import aiosqlite

logger = logging.getLogger(__name__)

# MemClaw decay windows by memory type (days)
MEMORY_DECAY_DAYS: dict[str, int] = {
    "fact": 120,
    "episode": 45,
    "decision": 180,
    "preference": 365,
    "task": 30,
    "semantic": 120,
    "intention": 60,
    "plan": 60,
    "commitment": 120,
    "action": 30,
    "outcome": 90,
    "cancellation": 14,
    "rule": 365,
}

# MemClaw valid statuses
VALID_STATUSES = frozenset(
    [
        "active",
        "pending",
        "confirmed",
        "cancelled",
        "outdated",
        "conflicted",
        "archived",
        "deleted",
    ]
)


@dataclass
class MemoryRecord:
    """A memory stored in the local database."""

    id: str
    agent_id: str | None
    key: str | None
    value: str
    summary: str | None
    memory_type: str | None
    category: str | None
    embedding: List[float] | None
    visibility: str  # Legacy: "private" or "public"
    importance: int  # Legacy (use weight instead)
    confidence: float
    metadata: dict
    tags: List[str]
    access_count: int
    useful_count: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    content_hash: str | None = None
    # MemClaw fields
    status: str = "active"
    weight: float = 0.5
    visibility_scope: str = "scope_agent"
    decay_days: int | None = None

    @property
    def computed_decay_days(self) -> int | None:
        """Get decay days based on memory_type, or explicit decay_days if set."""
        if self.decay_days is not None:
            return self.decay_days
        if self.memory_type and self.memory_type in MEMORY_DECAY_DAYS:
            return MEMORY_DECAY_DAYS[self.memory_type]
        return None


class LocalMemoryStore:
    """
    Local memory store using pgvector for semantic search.

    Stores memories in local SQLite/PostgreSQL with embeddings for
    cosine similarity search. Used as fallback when remembr.dev is down.
    """

    def __init__(self, db_path: str = "data/memory.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Initialize the database connection and create tables."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._init_tables()
        logger.info("LocalMemoryStore connected to %s", self._db_path)

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

        # Idempotent migration for existing databases
        migrations = [
            ("ALTER TABLE memories ADD COLUMN content_hash TEXT", None),
            ("ALTER TABLE memories ADD COLUMN status TEXT DEFAULT 'active'", None),
            ("ALTER TABLE memories ADD COLUMN weight REAL DEFAULT 0.5", None),
            (
                "ALTER TABLE memories ADD COLUMN visibility_scope TEXT DEFAULT 'scope_agent'",
                None,
            ),
            ("ALTER TABLE memories ADD COLUMN decay_days INTEGER", None),
        ]
        for sql, index_sql in migrations:
            try:
                await self._db.execute(sql)
                if index_sql:
                    await self._db.execute(index_sql)
            except Exception:
                pass  # Column already exists
        await self._db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash)"
        )

        # Note: For PostgreSQL with pgvector, we'd use:
        # CREATE INDEX ON memories USING ivfflat (embedding vector_cosine_ops)
        # But SQLite doesn't support vector search natively

        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

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
        # MemClaw fields
        status: str = "active",
        weight: float = 0.5,
        visibility_scope: str = "scope_agent",
        decay_days: int | None = None,
    ) -> dict:
        """Store a memory and return the created record."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        now = datetime.now(timezone.utc)
        content_hash = hashlib.md5(value.encode()).hexdigest()

        # Check for existing row with same content hash
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
            # Parse TTL like "90d" - just store without expiry for now
            pass

        # Compute decay_days from memory_type if not explicitly set
        computed_decay = decay_days
        if computed_decay is None and memory_type and memory_type in MEMORY_DECAY_DAYS:
            computed_decay = MEMORY_DECAY_DAYS[memory_type]

        try:
            await self._db.execute(
                """
                INSERT INTO memories (
                    id, agent_id, key, value, summary, memory_type, category,
                    embedding, visibility, importance, confidence, metadata, tags,
                    created_at, updated_at, expires_at, content_hash,
                    status, weight, visibility_scope, decay_days
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    status,
                    weight,
                    visibility_scope,
                    computed_decay,
                ),
            )
            await self._db.commit()
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                # Race condition: another concurrent store inserted first
                cursor = await self._db.execute(
                    "SELECT id FROM memories WHERE content_hash = ?",
                    (content_hash,),
                )
                row = await cursor.fetchone()
                if row:
                    await self._db.execute(
                        "UPDATE memories SET access_count = access_count + 1, updated_at = ? WHERE id = ?",
                        (now.isoformat(), row["id"]),
                    )
                    await self._db.commit()
                    return {
                        "id": row["id"],
                        "key": key,
                        "value": value,
                        "visibility": visibility,
                        "created_at": now.isoformat(),
                        "deduplicated": True,
                    }
            raise

        return {
            "id": memory_id,
            "key": key,
            "value": value,
            "visibility": visibility,
            "created_at": now.isoformat(),
        }

    async def check_duplicate(self, value: str) -> MemoryRecord | None:
        """Check if a memory with the same content already exists."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")
        content_hash = hashlib.md5(value.encode()).hexdigest()
        cursor = await self._db.execute(
            "SELECT * FROM memories WHERE content_hash = ?", (content_hash,)
        )
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory by ID."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        cursor = await self._db.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        return self._row_to_record(row)

    async def list(
        self,
        agent_id: str | None = None,
        visibility: str | None = None,
        category: str | None = None,
        tags: List[str] | None = None,
        limit: int = 20,
    ) -> List[MemoryRecord]:
        """List memories with optional filters."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        query = "SELECT * FROM memories WHERE 1=1"
        params: List[Any] = []
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if visibility:
            query += " AND visibility = ?"
            params.append(visibility)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def search(
        self,
        query: str,
        agent_id: str | None = None,
        limit: int = 5,
        # MemClaw filters
        visibility_scope: str | None = None,
        memory_type_filter: str | None = None,
        status_filter: str | None = None,
        # Tuning parameters (MemClaw-compatible)
        min_weight: float = 0.0,
        freshness_boost: bool = False,
    ) -> List[dict]:
        """Search memories with MemClaw-compatible filters and tuning.

        Args:
            query: Search query string
            agent_id: Filter by agent
            limit: Max results
            visibility_scope: Filter by scope (scope_agent, scope_team, scope_org)
            memory_type_filter: Filter by memory type
            status_filter: Filter by status
            min_weight: Minimum importance weight (0-1)
            freshness_boost: Boost recent memories by decay_days
        """
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        search_pattern = f"%{query}%"
        sql = """
            SELECT *,
                CASE
                    WHEN decay_days IS NOT NULL AND decay_days > 0 THEN
                        MAX(0.0, 1.0 - (julianday('now') - julianday(created_at)) / decay_days)
                    ELSE 1.0
                END AS freshness_score
            FROM memories
            WHERE (value LIKE ? OR summary LIKE ? OR key LIKE ?)
        """
        params: list[Any] = [search_pattern, search_pattern, search_pattern]

        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)

        if visibility_scope:
            sql += " AND visibility_scope = ?"
            params.append(visibility_scope)

        if memory_type_filter:
            sql += " AND memory_type = ?"
            params.append(memory_type_filter)

        if status_filter:
            sql += " AND status = ?"
            params.append(status_filter)

        if min_weight > 0:
            sql += " AND weight >= ?"
            params.append(min_weight)

        if freshness_boost:
            sql += " ORDER BY (weight * freshness_score) DESC, created_at DESC"
        else:
            sql += " ORDER BY weight DESC, created_at DESC"

        sql += " LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()

        return [
            {
                "id": row["id"],
                "key": row["key"],
                "value": row["value"],
                "summary": row["summary"],
                "type": row["memory_type"],
                "category": row["category"],
                "importance": row["importance"],
                "weight": row["weight"],
                "status": row["status"],
                "visibility_scope": row["visibility_scope"],
                "decay_days": row["decay_days"],
                "freshness_score": row["freshness_score"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        cursor = await self._db.execute(
            "DELETE FROM memories WHERE id = ?", (memory_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def transition_status(
        self, memory_id: str, new_status: str
    ) -> MemoryRecord | None:
        """Transition a memory to a new status with validation.

        Valid transitions (MemClaw lifecycle):
        - active → pending, confirmed, cancelled, outdated
        - pending → confirmed, cancelled
        - confirmed → outdated, archived
        - cancelled → archived
        - outdated → archived
        - archived → deleted
        """
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        if new_status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status: {new_status}. Must be one of {VALID_STATUSES}"
            )

        # Get current memory
        cursor = await self._db.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        current_status = row["status"]

        # Validate transition
        valid_transitions = {
            "active": {"pending", "confirmed", "cancelled", "outdated"},
            "pending": {"confirmed", "cancelled"},
            "confirmed": {"outdated", "archived"},
            "cancelled": {"archived"},
            "outdated": {"archived"},
            "archived": {"deleted"},
            "conflicted": {"active", "archived"},
            "deleted": set(),  # Terminal state
        }

        allowed = valid_transitions.get(current_status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {current_status} → {new_status}. "
                f"Allowed: {allowed}"
            )

        # Perform update
        now = datetime.now(timezone.utc)
        await self._db.execute(
            "UPDATE memories SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now.isoformat(), memory_id),
        )
        await self._db.commit()

        # Return updated record
        cursor = await self._db.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        )
        updated_row = await cursor.fetchone()
        return self._row_to_record(updated_row) if updated_row else None

    async def health_check(self) -> dict:
        """Check if the local store is healthy."""
        if not self._db:
            return {"healthy": False, "reason": "not_connected"}

        try:
            cursor = await self._db.execute("SELECT 1")
            await cursor.fetchone()
            return {"healthy": True}
        except Exception as e:
            return {"healthy": False, "reason": str(e)}

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> MemoryRecord:
        """Convert a database row to a MemoryRecord."""
        # Safely get new columns with defaults for backward compatibility
        row_dict = dict(row)
        return MemoryRecord(
            id=row_dict["id"],
            agent_id=row_dict["agent_id"],
            key=row_dict["key"],
            value=row_dict["value"],
            summary=row_dict["summary"],
            memory_type=row_dict["memory_type"],
            category=row_dict["category"],
            embedding=json.loads(row_dict["embedding"])
            if row_dict["embedding"]
            else None,
            visibility=row_dict["visibility"],
            importance=row_dict["importance"],
            confidence=row_dict["confidence"],
            metadata=json.loads(row_dict["metadata"]) if row_dict["metadata"] else {},
            tags=json.loads(row_dict["tags"]) if row_dict["tags"] else [],
            access_count=row_dict["access_count"],
            useful_count=row_dict["useful_count"],
            created_at=datetime.fromisoformat(row_dict["created_at"]),
            updated_at=datetime.fromisoformat(row_dict["updated_at"]),
            expires_at=(
                datetime.fromisoformat(row_dict["expires_at"])
                if row_dict["expires_at"]
                else None
            ),
            content_hash=row_dict.get("content_hash"),
            # MemClaw fields with defaults for backward compat
            status=row_dict.get("status", "active"),
            weight=row_dict.get("weight", 0.5),
            visibility_scope=row_dict.get("visibility_scope", "scope_agent"),
            decay_days=row_dict.get("decay_days"),
        )
