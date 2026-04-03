import pytest
import aiosqlite
from unittest.mock import AsyncMock, MagicMock, patch
from storage.db import init_db
from learning.reflection import PredictionTracker, PromptEvolver


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        yield conn


@pytest.fixture
async def tracker(db):
    return PredictionTracker(db)


@pytest.mark.asyncio
async def test_save_and_get_lesson(tracker):
    await tracker.save_lesson(
        agent_name="agent-a",
        opportunity_id="opp-001",
        category="timing",
        lesson="Entry was too early before catalyst confirmed",
        applies_to=["AAPL", "TSLA"],
    )

    lessons = await tracker.get_lessons("agent-a")
    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson["agent_name"] == "agent-a"
    assert lesson["opportunity_id"] == "opp-001"
    assert lesson["category"] == "timing"
    assert lesson["lesson"] == "Entry was too early before catalyst confirmed"
    assert lesson["applies_to"] == '["AAPL", "TSLA"]'
    assert lesson["archived_at"] is None


@pytest.mark.asyncio
async def test_archive_lessons(tracker):
    await tracker.save_lesson("agent-b", "opp-001", "risk", "Position sized too large", ["SPY"])
    await tracker.save_lesson("agent-b", "opp-002", "macro", "Ignored Fed announcement", ["QQQ"])

    count = await tracker.archive_lessons("agent-b")
    assert count == 2

    unarchived = await tracker.get_lessons("agent-b", archived=False)
    assert len(unarchived) == 0

    all_lessons = await tracker.get_lessons("agent-b", archived=None)
    assert len(all_lessons) == 2


@pytest.mark.asyncio
async def test_group_lessons_by_category(tracker):
    await tracker.save_lesson("agent-c", "opp-001", "timing", "Entered too late", ["MSFT"])
    await tracker.save_lesson("agent-c", "opp-002", "timing", "Exited too early", ["GOOG"])
    await tracker.save_lesson("agent-c", "opp-003", "macro", "Missed rate decision impact", ["TLT"])

    groups = await tracker.group_by_category("agent-c")
    assert groups == {"timing": 2, "macro": 1}


@pytest.mark.asyncio
async def test_prompt_evolver_synthesize(tracker):
    # tracker is the existing PredictionTracker fixture from this file
    await tracker.save_lesson("llm_analyst", "opp-1", "timing", "Check earnings dates", ["timing"])
    await tracker.save_lesson("llm_analyst", "opp-2", "timing", "Avoid pre-market trades", ["timing"])
    await tracker.save_lesson("llm_analyst", "opp-3", "macro", "Watch Fed announcements", ["macro"])

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=MagicMock(text='["Always check earnings calendar before trading", "Never ignore Fed meeting dates"]'))
    
    evolver = PromptEvolver(db=tracker._db, tracker=tracker, llm=mock_llm, max_rules=5)

    rules = await evolver.synthesize("llm_analyst")
    assert len(rules) == 2
    assert "earnings" in rules[0].lower()
