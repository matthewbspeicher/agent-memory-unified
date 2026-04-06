from __future__ import annotations
import aiosqlite
import pytest
from storage.db import init_db
from storage.spreads import SpreadStore, SpreadObservation


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


def _obs(k: str = "K1", p: str = "P1", gap: int = 10) -> SpreadObservation:
    return SpreadObservation(
        kalshi_ticker=k,
        poly_ticker=p,
        match_score=0.75,
        kalshi_cents=45,
        poly_cents=45 + gap,
        gap_cents=gap,
        kalshi_volume=1000.0,
        poly_volume=2000.0,
    )


class TestSpreadStore:
    async def test_record_and_get_history(self, db):
        store = SpreadStore(db)
        await store.record(_obs())
        history = await store.get_history("K1", "P1", hours=24)
        assert len(history) == 1
        assert history[0].gap_cents == 10

    async def test_get_history_empty(self, db):
        store = SpreadStore(db)
        history = await store.get_history("NONE", "NONE", hours=24)
        assert history == []

    async def test_get_history_multiple(self, db):
        store = SpreadStore(db)
        for gap in [5, 8, 12]:
            await store.record(_obs(gap=gap))
        history = await store.get_history("K1", "P1", hours=24)
        assert len(history) == 3
        gaps = [h.gap_cents for h in history]
        assert 5 in gaps and 8 in gaps and 12 in gaps

    async def test_get_history_hours_filter(self, db):
        store = SpreadStore(db)
        # Insert a row then query with 0 hours — should be empty
        await store.record(_obs())
        history = await store.get_history("K1", "P1", hours=0)
        assert history == []

    async def test_get_top_spreads(self, db):
        store = SpreadStore(db)
        await store.record(_obs("K1", "P1", gap=15))
        await store.record(_obs("K2", "P2", gap=3))
        top = await store.get_top_spreads(min_gap=5, limit=10)
        assert len(top) == 1
        assert top[0]["kalshi_ticker"] == "K1"
        assert top[0]["gap_cents"] == 15

    async def test_get_top_spreads_returns_only_latest_per_pair(self, db):
        """get_top_spreads must return the most-recent row per (kalshi,poly) pair."""
        from datetime import datetime, timezone, timedelta

        store = SpreadStore(db)
        now = datetime.now(timezone.utc)
        old_obs = SpreadObservation(
            kalshi_ticker="K1",
            poly_ticker="P1",
            match_score=0.8,
            kalshi_cents=45,
            poly_cents=55,
            gap_cents=10,
            observed_at=(now - timedelta(hours=2)).isoformat(),
        )
        new_obs = SpreadObservation(
            kalshi_ticker="K1",
            poly_ticker="P1",
            match_score=0.8,
            kalshi_cents=45,
            poly_cents=63,
            gap_cents=18,
            observed_at=now.isoformat(),
        )
        await store.record(old_obs)
        await store.record(new_obs)
        top = await store.get_top_spreads(min_gap=5, limit=10)
        assert len(top) == 1, "Should return exactly one row per pair"
        assert top[0]["gap_cents"] == 18, "Should return the most recent observation"

    async def test_record_swallows_errors(self, db):
        store = SpreadStore(db)
        # Close db to simulate write failure; record should not raise
        await db.close()
        obs = _obs()
        # Should log and swallow, not raise
        await store.record(obs)
