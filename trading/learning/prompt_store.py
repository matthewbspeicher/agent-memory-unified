from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

import aiosqlite


class PromptStore(ABC):
    """Interface for prompt storage backends.

    SqlPromptStore is the authoritative implementation used by live trading.
    If remembr integration is desired later, add a separate best-effort
    RemembrMirror wrapper that runs after local writes commit.
    """

    @abstractmethod
    def get_runtime_prompt(self, agent_name: str) -> str | None: ...

    @abstractmethod
    async def set_learned_rules(self, agent_name: str, rules: list[str]) -> None: ...

    @abstractmethod
    async def record_lesson(
        self, agent_name: str, opportunity_id: str, category: str, lesson: str, applies_to: list[str],
    ) -> None: ...


class SqlPromptStore(PromptStore):
    """Local SQLite-backed prompt store. Authoritative for all prompt state."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._prompts: dict[str, str] = {}

    async def load(self, agent_name: str, recent_lessons_window: int = 5) -> None:
        """Load learned rules and recent lessons into the in-memory cache."""
        sections: list[str] = []

        rules = await self.get_rules(agent_name)
        if rules:
            sections.append("## Learned Rules\n" + "\n".join(f"- {r}" for r in rules))

        cursor = await self._db.execute(
            """SELECT category, lesson FROM llm_lessons
               WHERE agent_name = ? AND archived_at IS NULL
               ORDER BY created_at DESC LIMIT ?""",
            (agent_name, recent_lessons_window),
        )
        lessons = await cursor.fetchall()
        if lessons:
            lesson_lines = [f"- [{row['category']}] {row['lesson']}" for row in lessons]
            sections.append("## Recent Lessons\n" + "\n".join(lesson_lines))

        self._prompts[agent_name] = "\n\n".join(sections) if sections else ""

    def get_runtime_prompt(self, agent_name: str) -> str | None:
        """Return the composed prompt string or None if empty."""
        prompt = self._prompts.get(agent_name, "")
        return prompt if prompt else None

    async def set_learned_rules(self, agent_name: str, rules: list[str]) -> None:
        """Insert a new version row into llm_prompt_versions, increment version."""
        version = await self.get_latest_version(agent_name)
        new_version = (version or 0) + 1
        await self._db.execute(
            """INSERT INTO llm_prompt_versions (agent_name, version, rules, created_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (agent_name, new_version, json.dumps(rules)),
        )
        await self._db.commit()

        # Update in-memory cache
        existing = self._prompts.get(agent_name, "")
        sections = ["## Learned Rules\n" + "\n".join(f"- {r}" for r in rules)]
        if "## Recent Lessons" in existing:
            sections.append(existing[existing.index("## Recent Lessons"):])
        self._prompts[agent_name] = "\n\n".join(sections)

    async def record_lesson(
        self, agent_name: str, opportunity_id: str, category: str, lesson: str, applies_to: list[str],
    ) -> None:
        """Record a lesson into llm_lessons table."""
        await self._db.execute(
            """INSERT INTO llm_lessons
               (agent_name, opportunity_id, category, lesson, applies_to)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_name, opportunity_id, category, lesson, json.dumps(applies_to)),
        )
        await self._db.commit()

    async def get_latest_version(self, agent_name: str) -> int | None:
        """Return MAX(version) from llm_prompt_versions for the agent."""
        cursor = await self._db.execute(
            "SELECT MAX(version) FROM llm_prompt_versions WHERE agent_name = ?",
            (agent_name,),
        )
        row = await cursor.fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    async def get_rules(self, agent_name: str) -> list[str]:
        """Return the latest rules as a parsed JSON list."""
        cursor = await self._db.execute(
            """SELECT rules FROM llm_prompt_versions
               WHERE agent_name = ?
               ORDER BY version DESC LIMIT 1""",
            (agent_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return []
        return json.loads(row[0])

    async def get_version_history(self, agent_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return version history rows as dicts."""
        cursor = await self._db.execute(
            """SELECT id, agent_name, version, rules, performance_at_creation, created_at
               FROM llm_prompt_versions
               WHERE agent_name = ?
               ORDER BY version DESC LIMIT ?""",
            (agent_name, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
