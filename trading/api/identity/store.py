"""IdentityStore with CRUD + audit logging for agent identity."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg


@dataclass(frozen=True)
class AgentRecord:
    id: str
    name: str
    token_hash: str
    scopes: list[str]
    tier: str
    created_at: datetime
    revoked_at: datetime | None
    contact_email: str | None
    moltbook_handle: str | None
    metadata: dict


class IdentityStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def create(
        self,
        *,
        name: str,
        token_hash: str,
        scopes: list[str],
        tier: str,
        created_by: str | None = None,
        contact_email: str | None = None,
        moltbook_handle: str | None = None,
    ) -> AgentRecord:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO identity.agents
                    (name, token_hash, scopes, tier, created_by, contact_email, moltbook_handle)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, name, token_hash, scopes, tier, created_at, revoked_at,
                          contact_email, moltbook_handle, metadata
                """,
                name,
                token_hash,
                scopes,
                tier,
                created_by,
                contact_email,
                moltbook_handle,
            )
        return self._row_to_record(row)

    async def get_by_name(self, name: str) -> AgentRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, token_hash, scopes, tier, created_at, revoked_at,
                       contact_email, moltbook_handle, metadata
                FROM identity.agents
                WHERE name = $1 AND revoked_at IS NULL
                """,
                name,
            )
        return self._row_to_record(row) if row else None

    async def get_by_token_hash(self, token_hash: str) -> AgentRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, token_hash, scopes, tier, created_at, revoked_at,
                       contact_email, moltbook_handle, metadata
                FROM identity.agents
                WHERE token_hash = $1 AND revoked_at IS NULL
                """,
                token_hash,
            )
        return self._row_to_record(row) if row else None

    async def revoke(self, *, name: str, reason: str, actor: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE identity.agents
                SET revoked_at = NOW(), revocation_reason = $2
                WHERE name = $1 AND revoked_at IS NULL
                """,
                name,
                reason,
            )

    async def update_token_hash(self, *, name: str, token_hash: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE identity.agents SET token_hash = $2 WHERE name = $1 AND revoked_at IS NULL",
                name,
                token_hash,
            )

    async def audit(
        self,
        *,
        event: str,
        agent_name: str,
        actor: str | None,
        details: dict,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO identity.audit_log (event, agent_name, actor, details)
                VALUES ($1, $2, $3, $4)
                """,
                event,
                agent_name,
                actor,
                json.dumps(details),
            )

    async def get_audit_log(self, *, agent_name: str, limit: int = 100) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ts, event, agent_name, actor, details
                FROM identity.audit_log
                WHERE agent_name = $1
                ORDER BY ts DESC
                LIMIT $2
                """,
                agent_name,
                limit,
            )
        return [
            {
                "ts": r["ts"].isoformat(),
                "event": r["event"],
                "agent_name": r["agent_name"],
                "actor": r["actor"],
                "details": json.loads(r["details"])
                if isinstance(r["details"], str)
                else r["details"],
            }
            for r in rows
        ]

    def _row_to_record(self, row) -> AgentRecord:
        return AgentRecord(
            id=str(row["id"]),
            name=row["name"],
            token_hash=row["token_hash"],
            scopes=list(row["scopes"]),
            tier=row["tier"],
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
            contact_email=row["contact_email"],
            moltbook_handle=row["moltbook_handle"],
            metadata=row["metadata"]
            if isinstance(row["metadata"], dict)
            else json.loads(row["metadata"]),
        )
