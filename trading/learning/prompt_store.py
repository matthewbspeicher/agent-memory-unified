from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
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
        self,
        agent_name: str,
        opportunity_id: str,
        category: str,
        lesson: str,
        applies_to: list[str],
    ) -> None: ...


class SqlPromptStore(PromptStore):
    """Local SQLite-backed prompt store. Authoritative for all prompt state."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._prompts: dict[str, str] = {}
        self._context_cache: dict[str, str] = {}

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
            sections.append(existing[existing.index("## Recent Lessons") :])
        self._prompts[agent_name] = "\n\n".join(sections)

    async def record_lesson(
        self,
        agent_name: str,
        opportunity_id: str,
        category: str,
        lesson: str,
        applies_to: list[str],
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

    async def get_version_history(
        self, agent_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
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

    # --- L0/L1 Layered Agent Context ---

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
            uni_str = ", ".join(str(u) for u in universe[:6])
            if len(agent_config.universe) > 6:
                uni_str += f" (+{len(agent_config.universe) - 6} more)"
        else:
            uni_str = str(universe)
        l0 = (
            f"## Identity\n"
            f"Agent: {agent_name} | Strategy: {agent_config.strategy} "
            f"| Action: {agent_config.action_level}\n"
            f"Universe: {uni_str} | Schedule: {agent_config.schedule}"
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
            sorted_mems = sorted(
                trade_memories, key=lambda m: m.get("importance", 0), reverse=True
            )
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
            """INSERT INTO agent_context_cache
               (agent_name, l0_text, l1_text, generated_at, trade_count)
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
