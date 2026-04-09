"""Tests for L0/L1 layered agent context in SqlPromptStore."""
from __future__ import annotations
from unittest.mock import MagicMock
import aiosqlite
import pytest
from learning.prompt_store import SqlPromptStore


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS llm_prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL, version INTEGER NOT NULL,
            rules TEXT NOT NULL, performance_at_creation TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS llm_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL, opportunity_id TEXT NOT NULL,
            category TEXT NOT NULL, lesson TEXT NOT NULL,
            applies_to TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            archived_at TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_context_cache (
            agent_name TEXT PRIMARY KEY, l0_text TEXT NOT NULL,
            l1_text TEXT NOT NULL, generated_at TEXT NOT NULL,
            trade_count INTEGER DEFAULT 0
        );
    """)
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
async def store(db):
    return SqlPromptStore(db)


def _make_config(name="rsi_scanner", strategy="RSI momentum",
                 action_level="suggest_trade", universe=None,
                 schedule="continuous", description="Test agent"):
    cfg = MagicMock()
    cfg.name = name
    cfg.strategy = strategy
    cfg.action_level = action_level
    cfg.universe = universe or ["AAPL", "MSFT"]
    cfg.schedule = schedule
    cfg.description = description
    return cfg


@pytest.mark.asyncio
async def test_l0_from_config(store):
    await store.generate_agent_context("rsi_scanner", _make_config())
    ctx = store.get_agent_context("rsi_scanner")
    assert "rsi_scanner" in ctx
    assert "RSI momentum" in ctx
    assert "suggest_trade" in ctx
    assert "AAPL" in ctx


@pytest.mark.asyncio
async def test_l1_empty_for_new_agent(store):
    await store.generate_agent_context("rsi_scanner", _make_config())
    ctx = store.get_agent_context("rsi_scanner")
    assert "no historical trades" in ctx.lower()


@pytest.mark.asyncio
async def test_l1_with_trade_memories(store):
    memories = [
        {"value": "AAPL +$340 win", "importance": 9},
        {"value": "MSFT -$180 loss", "importance": 8},
    ]
    await store.generate_agent_context("rsi_scanner", _make_config(), trade_memories=memories)
    ctx = store.get_agent_context("rsi_scanner")
    assert "AAPL" in ctx
    assert "MSFT" in ctx
    assert "no historical" not in ctx.lower()


@pytest.mark.asyncio
async def test_debounce(store):
    await store.generate_agent_context("rsi_scanner", _make_config())
    result = await store.maybe_regenerate_context("rsi_scanner", _make_config(), min_interval_minutes=30)
    assert result is False


@pytest.mark.asyncio
async def test_get_returns_none_when_empty(store):
    assert store.get_agent_context("nonexistent") is None


@pytest.mark.asyncio
async def test_cached_in_db(store):
    await store.generate_agent_context("rsi_scanner", _make_config())
    cursor = await store._db.execute(
        "SELECT * FROM agent_context_cache WHERE agent_name = ?", ("rsi_scanner",)
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row["l0_text"] != ""


@pytest.mark.asyncio
async def test_regime_context_in_l1(store):
    memories = [{"value": "BTC +$500", "importance": 10}]
    await store.generate_agent_context(
        "rsi_scanner", _make_config(), trade_memories=memories, regime_context="bull (since 2026-04-01)"
    )
    ctx = store.get_agent_context("rsi_scanner")
    assert "bull" in ctx
