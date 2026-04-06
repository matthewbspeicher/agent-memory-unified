"""Database-backed Agent Registry (PostgreSQL/SQLite).

Replaces static agents.yaml as runtime source of truth.
Follows Gemini design §1 with amendments from design review.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite

from storage.encoding import decode_json_columns

logger = logging.getLogger(__name__)

# Whitelist of allowed columns for partial updates (prevents SQL injection)
_ALLOWED_UPDATE_COLUMNS = frozenset(
    {
        "strategy",
        "schedule",
        "interval_or_cron",
        "universe",
        "parameters",
        "status",
        "trust_level",
        "runtime_overrides",
        "shadow_mode",
        "promotion_criteria",
        "parent_name",
        "generation",
        "creation_context",
    }
)

# Columns returned by get/get_all (excludes internal DB rowid)
_RETURN_COLUMNS = (
    "id, name, strategy, schedule, interval_or_cron, universe, parameters, "
    "status, trust_level, runtime_overrides, shadow_mode, promotion_criteria, "
    "created_by, parent_name, generation, creation_context, created_at, updated_at"
)


def _decode_agent_row(row: dict[str, Any]) -> dict[str, Any]:
    """Decode JSON columns in an agent row with type-appropriate fallbacks."""
    # Decode dict-type columns with {} fallback
    decode_json_columns(
        row,
        ["parameters", "runtime_overrides", "creation_context", "promotion_criteria"],
        fallback={},
    )
    # Decode universe (list-type column) with [] fallback
    decode_json_columns(row, ["universe"], fallback=[])
    return row


class AgentStore:
    """Repository for the agent_registry table."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Insert a new agent. Raises if name already exists."""
        name = entry["name"]
        await self._db.execute(
            """INSERT INTO agent_registry (
                name, strategy, schedule, interval_or_cron, universe, parameters,
                status, trust_level, runtime_overrides, shadow_mode, promotion_criteria,
                created_by, parent_name, generation, creation_context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                entry.get("strategy", ""),
                entry.get("schedule", "continuous"),
                entry.get("interval_or_cron", 60),
                json.dumps(entry.get("universe", [])),
                json.dumps(entry.get("parameters", {})),
                entry.get("status", "active"),
                entry.get("trust_level", "monitored"),
                json.dumps(entry.get("runtime_overrides", {})),
                int(entry.get("shadow_mode", False)),
                json.dumps(entry.get("promotion_criteria", {})),
                entry.get("created_by", "human"),
                entry.get("parent_name"),
                entry.get("generation", 1),
                json.dumps(entry.get("creation_context", {})),
            ),
        )
        await self._db.commit()
        return await self.get(name)

    async def get(self, name: str) -> dict[str, Any] | None:
        """Get agent by name."""
        cursor = await self._db.execute(
            f"SELECT {_RETURN_COLUMNS} FROM agent_registry WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _decode_agent_row(dict(row))

    async def get_all(self) -> list[dict[str, Any]]:
        """Get all agents."""
        cursor = await self._db.execute(
            f"SELECT {_RETURN_COLUMNS} FROM agent_registry ORDER BY created_at DESC"
        )
        return [_decode_agent_row(dict(row)) for row in await cursor.fetchall()]

    async def get_all_active(self) -> list[dict[str, Any]]:
        """Get all active agents (status = 'active')."""
        cursor = await self._db.execute(
            f"SELECT {_RETURN_COLUMNS} FROM agent_registry WHERE status = 'active' ORDER BY created_at DESC"
        )
        return [_decode_agent_row(dict(row)) for row in await cursor.fetchall()]

    async def list_all(self) -> list[dict[str, Any]]:
        """Alias for get_all()."""
        return await self.get_all()

    async def list_by_status(self, status: str) -> list[dict[str, Any]]:
        """List agents filtered by status."""
        cursor = await self._db.execute(
            f"SELECT {_RETURN_COLUMNS} FROM agent_registry WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )
        return [_decode_agent_row(dict(row)) for row in await cursor.fetchall()]

    async def list_active(self) -> list[dict[str, Any]]:
        """List active agents (alias for get_all_active)."""
        return await self.get_all_active()

    async def update(
        self, name: str, updates: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Partial update of agent fields. Only whitelisted columns allowed.

        Accepts updates as either a dict or keyword arguments:
            update("name", {"status": "dormant"})
            update("name", trust_level="trusted")
        """
        merged = {**(updates or {}), **kwargs}
        if not merged:
            return await self.get(name)

        # Filter to whitelisted columns only
        filtered = {k: v for k, v in merged.items() if k in _ALLOWED_UPDATE_COLUMNS}
        if not filtered:
            return await self.get(name)

        set_clauses = []
        values = []
        for col, val in filtered.items():
            set_clauses.append(f"{col} = ?")
            if col in (
                "universe",
                "parameters",
                "runtime_overrides",
                "creation_context",
                "promotion_criteria",
            ):
                values.append(json.dumps(val) if val is not None else None)
            else:
                values.append(val)

        set_clauses.append("updated_at = datetime('now')")
        values.append(name)

        sql = f"UPDATE agent_registry SET {', '.join(set_clauses)} WHERE name = ?"
        await self._db.execute(sql, values)
        await self._db.commit()
        return await self.get(name)

    async def upsert(self, name: str, entry: dict[str, Any]) -> dict[str, Any]:
        """Upsert agent (insert or replace if exists)."""
        existing = await self.get(name)
        if existing is None:
            return await self.create({"name": name, **entry})
        else:
            return await self.update(name, entry)

    async def set_status(self, name: str, status: str) -> dict[str, Any] | None:
        """Set agent status (active, dormant, retired)."""
        return await self.update(name, {"status": status})

    async def set_trust_level(
        self, name: str, trust_level: str
    ) -> dict[str, Any] | None:
        """Set agent trust level (monitored, trusted)."""
        return await self.update(name, {"trust_level": trust_level})

    async def set_shadow_mode(
        self, name: str, shadow_mode: bool
    ) -> dict[str, Any] | None:
        """Enable/disable shadow mode for an agent."""
        return await self.update(name, {"shadow_mode": int(shadow_mode)})

    async def soft_delete(self, name: str) -> dict[str, Any] | None:
        """Soft delete by setting status to 'retired'."""
        return await self.set_status(name, "retired")

    async def create_evolved_agent(
        self,
        name: str,
        strategy: str,
        parent_name: str,
        parameters: dict[str, Any] | None = None,
        universe: list[str] | None = None,
        creation_context: dict[str, Any] | None = None,
        generation: int | None = None,
    ) -> dict[str, Any]:
        """Create a Hermes-evolved agent with safety defaults.

        Key safety features:
        - shadow_mode=True by default (agents must be promoted to go live)
        - created_by='hermes' for lineage tracking
        - parent_name and generation for evolutionary tracking
        """
        # Determine generation from parent if not specified
        if generation is None:
            parent = await self.get(parent_name)
            if parent:
                generation = parent.get("generation", 0) + 1
            else:
                generation = 1

        entry = {
            "strategy": strategy,
            "schedule": "continuous",
            "interval_or_cron": 60,
            "universe": universe or [],
            "parameters": parameters or {},
            "status": "active",
            "trust_level": "monitored",
            "runtime_overrides": {},
            "shadow_mode": True,  # SAFETY: Always True for evolved agents
            "created_by": "hermes",
            "parent_name": parent_name,
            "generation": generation,
            "creation_context": creation_context or {},
        }
        return await self.create({"name": name, **entry})

    async def seed_from_yaml(self, yaml_agents: list[dict[str, Any]]) -> int:
        """Seed agent_registry from YAML config. Returns count of new agents added.

        This is called once on first boot when the table is empty.
        After seeding, the database becomes the authoritative source.
        """
        count = 0
        for agent in yaml_agents:
            name = agent.get("name")
            if name is None:
                continue
            existing = await self.get(name)
            if existing is not None:
                continue

            # Map YAML schema to registry columns
            entry = {
                "strategy": agent.get("strategy", ""),
                "schedule": agent.get("schedule", "continuous"),
                "interval_or_cron": agent.get(
                    "interval", agent.get("interval_or_cron", 60)
                ),
                "universe": agent.get("universe", []),
                "parameters": agent.get("parameters", {}),
                "status": "active",
                "trust_level": agent.get("trust_level", "monitored"),
                "runtime_overrides": {},
                # YAML agents respect explicit shadow_mode; default False for backwards compat
                "shadow_mode": agent.get("shadow_mode", False),
                "created_by": "human",
                "parent_name": None,
                "generation": 1,
                "creation_context": {},
            }
            await self.create({"name": name, **entry})
            count += 1

        if count > 0:
            logger.info(f"Seeded {count} agents from YAML into agent_registry")
        return count

    # --- Trust tracking ---

    async def log_trust_change(
        self, agent_name: str, old_level: str, new_level: str, changed_by: str
    ) -> None:
        """Insert trust change event into trust_events table."""
        await self._db.execute(
            """INSERT INTO trust_events (agent_name, old_level, new_level, changed_by, changed_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (agent_name, old_level, new_level, changed_by),
        )
        await self._db.commit()

    async def get_trust_history(
        self, agent_name: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Query trust_events for an agent."""
        cursor = await self._db.execute(
            "SELECT * FROM trust_events WHERE agent_name = ? ORDER BY changed_at DESC LIMIT ?",
            (agent_name, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
