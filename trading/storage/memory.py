"""Local Memory Store with pgvector for hybrid memory architecture.

Provides local fallback when remembr.dev is unavailable.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


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
    embedding: list[float] | None
    visibility: str  # "private" or "public"
    importance: int
    confidence: float
    metadata: dict
    tags: list[str]
    access_count: int
    useful_count: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


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
                expires_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
            CREATE INDEX IF NOT EXISTS idx_memories_visibility ON memories(visibility);
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
        """)

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
        embedding: list[float] | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        importance: int = 5,
        confidence: float = 0.5,
        ttl: str | None = None,
    ) -> dict:
        """Store a memory and return the created record."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = None
        if ttl:
            # Parse TTL like "90d" - just store without expiry for now
            pass

        await self._db.execute(
            """
            INSERT INTO memories (
                id, agent_id, key, value, summary, memory_type, category,
                embedding, visibility, importance, confidence, metadata, tags,
                created_at, updated_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """List memories with optional filters."""
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        query = "SELECT * FROM memories WHERE 1=1"
        params: list[Any] = []
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
    ) -> list[dict]:
        """
        Search memories by text (keyword search).

        Note: True semantic search requires embeddings and pgvector.
        This implements basic keyword matching as fallback.
        """
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        # Basic keyword search (for full semantic search, we'd need embeddings)
        search_pattern = f"%{query}%"
        sql = """
            SELECT * FROM memories
            WHERE (value LIKE ? OR summary LIKE ? OR key LIKE ?)
        """
        params = [search_pattern, search_pattern, search_pattern]

        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)

        sql += " ORDER BY importance DESC, created_at DESC LIMIT ?"
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
        return MemoryRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            key=row["key"],
            value=row["value"],
            summary=row["summary"],
            memory_type=row["memory_type"],
            category=row["category"],
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
            visibility=row["visibility"],
            importance=row["importance"],
            confidence=row["confidence"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            tags=json.loads(row["tags"]) if row["tags"] else [],
            access_count=row["access_count"],
            useful_count=row["useful_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            expires_at=(
                datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
            ),
        )
