from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class PredictionTracker:
    def __init__(self, db: aiosqlite.Connection, prompt_store: Any = None) -> None:
        self._db = db
        self._prompt_store = prompt_store

    async def save_lesson(
        self,
        agent_name: str,
        opportunity_id: str,
        category: str,
        lesson: str,
        applies_to: list[str],
    ) -> None:
        if self._prompt_store:
            await self._prompt_store.record_lesson(
                agent_name, opportunity_id, category, lesson, applies_to
            )
        else:
            await self._db.execute(
                """INSERT INTO llm_lessons (agent_name, opportunity_id, category, lesson, applies_to)
                   VALUES (?, ?, ?, ?, ?)""",
                (agent_name, opportunity_id, category, lesson, json.dumps(applies_to)),
            )
            await self._db.commit()

    async def get_lessons(
        self,
        agent_name: str,
        archived: bool | None = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM llm_lessons WHERE agent_name = ?"
        params: list[Any] = [agent_name]

        if archived is False:
            query += " AND archived_at IS NULL"
        elif archived is True:
            query += " AND archived_at IS NOT NULL"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def archive_lessons(self, agent_name: str) -> int:
        cursor = await self._db.execute(
            """UPDATE llm_lessons SET archived_at = datetime('now')
               WHERE agent_name = ? AND archived_at IS NULL""",
            (agent_name,),
        )
        await self._db.commit()
        return cursor.rowcount

    async def group_by_category(self, agent_name: str) -> dict[str, int]:
        cursor = await self._db.execute(
            """SELECT category, COUNT(*) FROM llm_lessons
               WHERE agent_name = ? AND archived_at IS NULL
               GROUP BY category""",
            (agent_name,),
        )
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}


class PromptEvolver:
    def __init__(
        self,
        db: aiosqlite.Connection,
        tracker: PredictionTracker,
        llm: Any = None,  # LLMClient | None
        max_rules: int = 10,
    ) -> None:
        self._db = db
        self._tracker = tracker
        if llm is not None:
            self._llm = llm
        else:
            from llm.client import LLMClient as _LLMClient

            self._llm = _LLMClient()
        self._max_rules = max_rules

    async def synthesize(self, agent_name: str) -> list[str]:
        try:
            lessons = await self._tracker.get_lessons(agent_name)
            if not lessons:
                return []

            by_category = await self._tracker.group_by_category(agent_name)
            category_summary = ", ".join(
                f"{cat}: {count}" for cat, count in by_category.items()
            )

            lessons_text = "\n".join(
                f"- [{row['category']}] {row['lesson']}" for row in lessons
            )

            prompt = (
                f"You are a trading strategy coach. Review these lessons learned by agent '{agent_name}'.\n\n"
                f"Category distribution: {category_summary}\n\n"
                f"Lessons:\n{lessons_text}\n\n"
                "Synthesize 3-5 concise trading rules. Each rule must start with 'Always', 'Never', or 'When'.\n"
                "Respond with a JSON array of strings only, no other text."
            )

            result = await self._llm.complete(prompt, max_tokens=512)
            content = (result.text or "").strip()
            if not content:
                return []

            match = __import__("re").search(r"\[.*\]", content, __import__("re").DOTALL)
            if match:
                content = match.group(0)
            rules: list[str] = json.loads(content)
            return rules[: self._max_rules]

        except Exception:
            logger.exception("PromptEvolver.synthesize failed for agent %s", agent_name)
            return []
