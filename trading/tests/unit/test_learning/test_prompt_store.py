import pytest
import aiosqlite
from storage.db import init_db
from learning.prompt_store import SqlPromptStore


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        yield conn


@pytest.fixture
async def store(db):
    return SqlPromptStore(db)


@pytest.mark.asyncio
async def test_get_runtime_prompt_returns_none_when_empty(store):
    result = store.get_runtime_prompt("agent-x")
    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_learned_rules(store):
    rules = ["Always set stop-loss", "Avoid low-volume symbols"]
    await store.set_learned_rules("agent-1", rules)

    prompt = store.get_runtime_prompt("agent-1")
    assert prompt is not None
    assert "## Learned Rules" in prompt
    assert "Always set stop-loss" in prompt
    assert "Avoid low-volume symbols" in prompt


@pytest.mark.asyncio
async def test_get_runtime_prompt_includes_recent_lessons(db, store):
    await db.execute(
        """INSERT INTO llm_lessons (agent_name, opportunity_id, category, lesson, applies_to)
           VALUES (?, ?, ?, ?, ?)""",
        ("agent-2", "opp-001", "risk", "Do not overtrade volatile symbols", "all"),
    )
    await db.commit()

    await store.load("agent-2")

    prompt = store.get_runtime_prompt("agent-2")
    assert prompt is not None
    assert "## Recent Lessons" in prompt
    assert "[risk] Do not overtrade volatile symbols" in prompt


@pytest.mark.asyncio
async def test_get_latest_version(store):
    assert await store.get_latest_version("agent-3") is None

    await store.set_learned_rules("agent-3", ["Rule A"])
    assert await store.get_latest_version("agent-3") == 1

    await store.set_learned_rules("agent-3", ["Rule A", "Rule B"])
    assert await store.get_latest_version("agent-3") == 2
