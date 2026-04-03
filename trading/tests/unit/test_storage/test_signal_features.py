"""Unit tests for SignalFeatureStore."""
from __future__ import annotations

import json

import aiosqlite
import pytest

from storage.db import init_db
from storage.signal_features import SignalFeatureStore


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield SignalFeatureStore(db)
    await db.close()


def _row(opportunity_id: str = "opp-001", **overrides) -> dict:
    defaults = {
        "agent_name": "rsi_agent",
        "symbol": "AAPL",
        "signal": "rsi_oversold",
        "asset_type": "STOCK",
        "confidence": 0.85,
        "opportunity_timestamp": "2026-03-31T10:00:00+00:00",
        "captured_at": "2026-03-31T10:00:01+00:00",
        "feature_version": "1.0",
        "rsi_14": 28.5,
        "sma_20": 172.0,
        "ema_20": 173.5,
        "macd_histogram": -0.42,
        "bollinger_pct_b": 0.12,
        "atr_14": 3.2,
        "realized_vol_20d": 0.22,
        "relative_volume_20d": 1.8,
        "feature_payload": {"action_level": "notify"},
        "capture_status": "captured",
    }
    defaults.update(overrides)
    return defaults


class TestSignalFeatureStore:
    async def test_upsert_and_get(self, store: SignalFeatureStore):
        row = _row()
        await store.upsert("opp-001", **row)

        result = await store.get("opp-001")
        assert result is not None
        assert result["opportunity_id"] == "opp-001"
        assert result["agent_name"] == "rsi_agent"
        assert result["symbol"] == "AAPL"
        assert result["rsi_14"] == pytest.approx(28.5)
        assert result["capture_status"] == "captured"

    async def test_feature_payload_decoded_as_dict(self, store: SignalFeatureStore):
        await store.upsert("opp-002", **_row("opp-002", feature_payload={"x": 1, "y": "z"}))
        result = await store.get("opp-002")
        assert isinstance(result["feature_payload"], dict)
        assert result["feature_payload"]["x"] == 1

    async def test_idempotent_upsert(self, store: SignalFeatureStore):
        await store.upsert("opp-003", **_row("opp-003", rsi_14=30.0))
        await store.upsert("opp-003", **_row("opp-003", rsi_14=35.0))

        result = await store.get("opp-003")
        assert result["rsi_14"] == pytest.approx(35.0)
        # Only one row should exist
        rows = await store.list_filtered()
        assert sum(1 for r in rows if r["opportunity_id"] == "opp-003") == 1

    async def test_get_returns_none_for_missing(self, store: SignalFeatureStore):
        result = await store.get("does-not-exist")
        assert result is None

    async def test_list_filtered_by_agent(self, store: SignalFeatureStore):
        await store.upsert("opp-a1", **_row("opp-a1", agent_name="agent_a"))
        await store.upsert("opp-b1", **_row("opp-b1", agent_name="agent_b"))
        await store.upsert("opp-a2", **_row("opp-a2", agent_name="agent_a"))

        results = await store.list_filtered(agent_name="agent_a")
        assert len(results) == 2
        assert all(r["agent_name"] == "agent_a" for r in results)

    async def test_list_filtered_by_symbol(self, store: SignalFeatureStore):
        await store.upsert("opp-s1", **_row("opp-s1", symbol="AAPL"))
        await store.upsert("opp-s2", **_row("opp-s2", symbol="MSFT"))

        results = await store.list_filtered(symbol="AAPL")
        assert len(results) == 1
        assert results[0]["symbol"] == "AAPL"

    async def test_list_filtered_by_signal(self, store: SignalFeatureStore):
        await store.upsert("opp-sig1", **_row("opp-sig1", signal="rsi_oversold"))
        await store.upsert("opp-sig2", **_row("opp-sig2", signal="macd_cross"))

        results = await store.list_filtered(signal="macd_cross")
        assert len(results) == 1
        assert results[0]["signal"] == "macd_cross"

    async def test_list_filtered_limit(self, store: SignalFeatureStore):
        for i in range(5):
            await store.upsert(f"opp-lim{i}", **_row(f"opp-lim{i}"))

        results = await store.list_filtered(limit=3)
        assert len(results) == 3

    async def test_null_safe_fields(self, store: SignalFeatureStore):
        """Columns not provided should be NULL, not cause errors."""
        await store.upsert(
            "opp-null",
            agent_name="rsi_agent",
            symbol="AAPL",
            signal="rsi_oversold",
            confidence=0.5,
            opportunity_timestamp="2026-03-31T10:00:00+00:00",
            captured_at="2026-03-31T10:00:01+00:00",
            feature_version="1.0",
            capture_status="partial",
        )
        result = await store.get("opp-null")
        assert result is not None
        assert result["rsi_14"] is None
        assert result["atr_14"] is None
        assert result["capture_status"] == "partial"

    async def test_list_by_agent(self, store: SignalFeatureStore):
        await store.upsert("opp-la1", **_row("opp-la1", agent_name="ag1"))
        await store.upsert("opp-la2", **_row("opp-la2", agent_name="ag2"))

        results = await store.list_by_agent("ag1")
        assert len(results) == 1
        assert results[0]["agent_name"] == "ag1"

    async def test_list_by_symbol(self, store: SignalFeatureStore):
        await store.upsert("opp-ls1", **_row("opp-ls1", symbol="TSLA"))
        await store.upsert("opp-ls2", **_row("opp-ls2", symbol="TSLA", agent_name="other"))

        results = await store.list_by_symbol("TSLA")
        assert len(results) == 2

        results_filtered = await store.list_by_symbol("TSLA", agent_name="rsi_agent")
        assert len(results_filtered) == 1
