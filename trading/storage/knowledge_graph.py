"""Temporal Knowledge Graph backed by SQLite.

Stores entities and time-stamped triples (subject-predicate-object) with
optional validity windows, confidence scores, and provenance metadata.
Designed for trading-domain facts that change over time.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)


class TradingKnowledgeGraph:
    """SQLite-backed temporal entity-relationship graph."""

    def __init__(self, db_path: str = "data/knowledge_graph.sqlite3"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open DB, enable WAL + busy_timeout, create tables."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._init_tables()
        logger.info("TradingKnowledgeGraph connected to %s", self._db_path)

    async def _init_tables(self) -> None:
        if not self._db:
            raise RuntimeError("Not connected - call connect() first")

        await self._db.executescript("""
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

            CREATE INDEX IF NOT EXISTS idx_kg_triples_subject
                ON kg_triples(subject);
            CREATE INDEX IF NOT EXISTS idx_kg_triples_object
                ON kg_triples(object);
            CREATE INDEX IF NOT EXISTS idx_kg_triples_predicate
                ON kg_triples(predicate);
            CREATE INDEX IF NOT EXISTS idx_kg_triples_validity
                ON kg_triples(valid_from, valid_to);
        """)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entity_id(name: str) -> str:
        """Normalize name to an entity id: lowercase, spaces to underscores, strip apostrophes."""
        return name.strip().lower().replace("'", "").replace(" ", "_")

    @staticmethod
    def _triple_to_dict(row) -> dict:
        """Convert an aiosqlite Row from kg_triples to a plain dict."""
        props_raw = row["properties"] if row["properties"] else "{}"
        return {
            "id": row["id"],
            "subject": row["subject"],
            "predicate": row["predicate"],
            "object": row["object"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "confidence": row["confidence"],
            "source": row["source"],
            "properties": json.loads(props_raw),
            "invalidation_reason": row["invalidation_reason"],
        }

    # ------------------------------------------------------------------
    # Entity operations
    # ------------------------------------------------------------------

    async def add_entity(
        self,
        name: str,
        entity_type: str = "unknown",
        properties: dict | None = None,
    ) -> str:
        """Insert or update an entity. Returns the entity id."""
        if not self._db:
            raise RuntimeError("Not connected")

        eid = self._entity_id(name)
        props_json = json.dumps(properties or {})
        now = datetime.now(timezone.utc).isoformat()

        await self._db.execute(
            """
            INSERT INTO kg_entities (id, name, entity_type, properties, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                entity_type = excluded.entity_type,
                properties = excluded.properties
            """,
            (eid, name, entity_type, props_json, now),
        )
        await self._db.commit()
        return eid

    # ------------------------------------------------------------------
    # Triple operations
    # ------------------------------------------------------------------

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
        """Add a triple, auto-creating entities. Returns the triple id.

        Idempotent: re-inserting the same triple returns the existing id.
        """
        if not self._db:
            raise RuntimeError("Not connected")

        sub_id = await self.add_entity(subject)
        obj_id = await self.add_entity(obj)

        # Deterministic triple id
        hash_input = f"{sub_id}:{predicate}:{obj_id}"
        md5 = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        triple_id = f"t_{sub_id}_{predicate}_{obj_id}_{md5}"

        # Check for existing (idempotent)
        cursor = await self._db.execute(
            "SELECT id FROM kg_triples WHERE id = ?", (triple_id,)
        )
        existing = await cursor.fetchone()
        if existing:
            return triple_id

        props_json = json.dumps(properties or {})
        now = datetime.now(timezone.utc).isoformat()

        await self._db.execute(
            """
            INSERT INTO kg_triples
                (id, subject, predicate, object, valid_from, valid_to,
                 confidence, source, properties, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                triple_id, sub_id, predicate, obj_id,
                valid_from, valid_to, confidence, source, props_json, now,
            ),
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
        """Mark matching active triples as expired."""
        if not self._db:
            raise RuntimeError("Not connected")

        sub_id = self._entity_id(subject)
        obj_id = self._entity_id(obj)
        ended = ended or datetime.now(timezone.utc).isoformat()

        await self._db.execute(
            """
            UPDATE kg_triples
            SET valid_to = ?, invalidation_reason = ?
            WHERE subject = ? AND predicate = ? AND object = ?
              AND valid_to IS NULL
            """,
            (ended, reason, sub_id, predicate, obj_id),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    async def query_entity(
        self,
        name: str,
        as_of: str | None = None,
        direction: str = "outgoing",
    ) -> list[dict]:
        """Query triples related to an entity.

        direction: "outgoing" (entity is subject), "incoming" (entity is object),
                   or "both".
        """
        if not self._db:
            raise RuntimeError("Not connected")

        eid = self._entity_id(name)
        time_clause = ""
        params: list = []

        if direction == "outgoing":
            base = "SELECT * FROM kg_triples WHERE subject = ?"
            params.append(eid)
        elif direction == "incoming":
            base = "SELECT * FROM kg_triples WHERE object = ?"
            params.append(eid)
        else:  # both
            base = "SELECT * FROM kg_triples WHERE subject = ? OR object = ?"
            params.extend([eid, eid])

        if as_of:
            time_clause = (
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to >= ?)"
            )
            params.extend([as_of, as_of])

        sql = base + time_clause
        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._triple_to_dict(r) for r in rows]

    async def query_relationship(
        self,
        predicate: str,
        as_of: str | None = None,
    ) -> list[dict]:
        """All triples with the given predicate, optionally filtered by time."""
        if not self._db:
            raise RuntimeError("Not connected")

        params: list = [predicate]
        sql = "SELECT * FROM kg_triples WHERE predicate = ?"

        if as_of:
            sql += (
                " AND (valid_from IS NULL OR valid_from <= ?)"
                " AND (valid_to IS NULL OR valid_to >= ?)"
            )
            params.extend([as_of, as_of])

        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._triple_to_dict(r) for r in rows]

    async def timeline(
        self,
        entity_name: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Chronological list of triples ordered by valid_from ASC."""
        if not self._db:
            raise RuntimeError("Not connected")

        if entity_name:
            eid = self._entity_id(entity_name)
            sql = (
                "SELECT * FROM kg_triples WHERE subject = ? OR object = ? "
                "ORDER BY COALESCE(valid_from, '0000') ASC LIMIT ?"
            )
            params: list = [eid, eid, limit]
        else:
            sql = (
                "SELECT * FROM kg_triples "
                "ORDER BY COALESCE(valid_from, '0000') ASC LIMIT ?"
            )
            params = [limit]

        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._triple_to_dict(r) for r in rows]

    async def stats(self) -> dict:
        """Return summary statistics about the knowledge graph."""
        if not self._db:
            raise RuntimeError("Not connected")

        entities = await (
            await self._db.execute("SELECT COUNT(*) FROM kg_entities")
        ).fetchone()

        triples = await (
            await self._db.execute("SELECT COUNT(*) FROM kg_triples")
        ).fetchone()

        current = await (
            await self._db.execute(
                "SELECT COUNT(*) FROM kg_triples WHERE valid_to IS NULL"
            )
        ).fetchone()

        expired = await (
            await self._db.execute(
                "SELECT COUNT(*) FROM kg_triples WHERE valid_to IS NOT NULL"
            )
        ).fetchone()

        rel_types = await (
            await self._db.execute(
                "SELECT DISTINCT predicate FROM kg_triples"
            )
        ).fetchall()

        return {
            "entities": entities[0],
            "triples": triples[0],
            "current_facts": current[0],
            "expired_facts": expired[0],
            "relationship_types": [r[0] for r in rel_types],
        }
