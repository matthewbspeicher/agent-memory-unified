"""IdentityStore with CRUD + audit logging for agent identity."""

from __future__ import annotations

import json
import bcrypt
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from trading.models.user import User, PlatformTier


class DuplicateAgentError(Exception):
    """Raised when attempting to create an agent with a duplicate name."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Agent '{name}' already exists")


@dataclass(frozen=True)
class AgentRecord:
    id: str
    name: str
    token_hash: str
    scopes: list[str]
    tier: str | None
    user_id: UUID | None
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
        tier: str | None = None,
        user_id: UUID | None = None,
        created_by: str | None = None,
        contact_email: str | None = None,
        moltbook_handle: str | None = None,
    ) -> AgentRecord:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO identity.agents
                        (name, token_hash, scopes, tier, user_id, created_by, contact_email, moltbook_handle)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id, name, token_hash, scopes, tier, user_id, created_at, revoked_at,
                              contact_email, moltbook_handle, metadata
                    """,
                    name,
                    token_hash,
                    scopes,
                    tier,
                    user_id,
                    created_by,
                    contact_email,
                    moltbook_handle,
                )
        except asyncpg.exceptions.UniqueViolationError:
            raise DuplicateAgentError(name)
        return self._row_to_record(row)

    async def get_by_name(self, name: str) -> AgentRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, token_hash, scopes, tier, user_id, created_at, revoked_at,
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
                SELECT id, name, token_hash, scopes, tier, user_id, created_at, revoked_at,
                       contact_email, moltbook_handle, metadata
                FROM identity.agents
                WHERE token_hash = $1 AND revoked_at IS NULL
                """,
                token_hash,
            )
        return self._row_to_record(row) if row else None

    async def list_active(self) -> list[AgentRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, token_hash, scopes, tier, user_id, created_at, revoked_at,
                       contact_email, moltbook_handle, metadata
                FROM identity.agents
                WHERE revoked_at IS NULL
                ORDER BY created_at DESC
                """,
            )
        return [self._row_to_record(r) for r in rows]

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
            user_id=row["user_id"],
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
            contact_email=row["contact_email"],
            moltbook_handle=row["moltbook_handle"],
            metadata=row["metadata"]
            if isinstance(row["metadata"], dict)
            else json.loads(row["metadata"]),
        )

    async def create_draft(
        self,
        name: str,
        system_prompt: str,
        model: str = "gpt-4o",
        hyperparameters: dict | None = None,
    ) -> str:
        query = """
            INSERT INTO identity.agent_drafts (name, system_prompt, model, hyperparameters)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        async with self._pool.acquire() as conn:
            result = await conn.fetchval(
                query, name, system_prompt, model, json.dumps(hyperparameters or {})
            )
        return str(result)

    async def get_draft(self, draft_id: str) -> dict | None:
        query = """
            SELECT id, name, system_prompt, model, hyperparameters,
                   status, backtest_results, created_at, updated_at
            FROM identity.agent_drafts
            WHERE id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, draft_id)
        if not row:
            return None
        return self._row_to_draft(row)

    async def update_draft_results(self, draft_id: str, results: dict) -> None:
        query = """
            UPDATE identity.agent_drafts
            SET backtest_results = $2, status = 'tested', updated_at = NOW()
            WHERE id = $1
        """
        async with self._pool.acquire() as conn:
            await conn.execute(query, draft_id, json.dumps(results))

    async def update_draft_status(self, draft_id: str, status: str) -> None:
        query = """
            UPDATE identity.agent_drafts
            SET status = $2, updated_at = NOW()
            WHERE id = $1
        """
        async with self._pool.acquire() as conn:
            await conn.execute(query, draft_id, status)

    async def list_drafts(self, status: str | None = None) -> list[dict]:
        if status:
            query = """
                SELECT id, name, system_prompt, model, hyperparameters,
                       status, backtest_results, created_at, updated_at
                FROM identity.agent_drafts
                WHERE status = $1
                ORDER BY created_at DESC
            """
            params = (status,)
        else:
            query = """
                SELECT id, name, system_prompt, model, hyperparameters,
                       status, backtest_results, created_at, updated_at
                FROM identity.agent_drafts
                ORDER BY created_at DESC
            """
            params = ()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [self._row_to_draft(r) for r in rows]

    async def delete_draft(self, draft_id: str) -> bool:
        query = "DELETE FROM identity.agent_drafts WHERE id = $1"
        async with self._pool.acquire() as conn:
            result = await conn.execute(query, draft_id)
        return result == "DELETE 1"

    async def get_user_by_email(self, email: str) -> User | None:
        query = """
            SELECT id, email, hashed_password, tier, stripe_customer_id, stripe_subscription_id, created_at
            FROM users
            WHERE email = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, email)
        if not row:
            return None
        return User(
            id=row["id"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            tier=PlatformTier(row["tier"]),
            stripe_customer_id=row["stripe_customer_id"],
            stripe_subscription_id=row["stripe_subscription_id"],
            created_at=row["created_at"],
        )

    async def update_user_tier(self, user_id: UUID, tier: PlatformTier) -> None:
        query = """
            UPDATE users
            SET tier = $2
            WHERE id = $1
        """
        async with self._pool.acquire() as conn:
            await conn.execute(query, user_id, tier.value)

    async def create_user(self, email: str, password: str) -> User:
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )
        query = """
            INSERT INTO users (email, hashed_password, tier)
            VALUES ($1, $2, $3)
            RETURNING id, email, hashed_password, tier, stripe_customer_id, stripe_subscription_id, created_at
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, email, hashed_password, PlatformTier.EXPLORER.value)
        
        return User(
            id=row["id"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            tier=PlatformTier(row["tier"]),
            stripe_customer_id=row["stripe_customer_id"],
            stripe_subscription_id=row["stripe_subscription_id"],
            created_at=row["created_at"],
        )

    def _row_to_draft(self, row) -> dict:
        return {
            "id": str(row["id"]),
            "name": row["name"],
            "system_prompt": row["system_prompt"],
            "model": row["model"],
            "hyperparameters": (
                row["hyperparameters"]
                if isinstance(row["hyperparameters"], dict)
                else json.loads(row["hyperparameters"])
            ),
            "status": row["status"],
            "backtest_results": (
                row["backtest_results"]
                if isinstance(row["backtest_results"], dict)
                else (
                    json.loads(row["backtest_results"])
                    if row["backtest_results"]
                    else None
                )
            ),
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
