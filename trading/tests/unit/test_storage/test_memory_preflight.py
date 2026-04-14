"""Tests for LocalMemoryStore._preflight_check.

Covers the preflight added in §C 0.3 of the delta roadmap — verifies the
store reports schema issues clearly rather than letting them surface as
opaque query errors later.
"""

from __future__ import annotations

import pytest

from storage.memory import LocalMemoryStore


@pytest.fixture
async def store(tmp_path):
    s = LocalMemoryStore(db_path=str(tmp_path / "preflight.db"))
    await s.connect()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_preflight_passes_on_fresh_store(store):
    result = await store._preflight_check()
    assert result["ok"] is True
    checks = result["checks"]
    assert checks["connection"] is True
    assert checks["schema"]["ok"] is True
    assert checks["schema"]["missing_columns"] == []
    assert checks["dedup_index"] is True
    assert checks["row_count"] == 0


@pytest.mark.asyncio
async def test_preflight_reports_row_count_after_writes(store):
    await store.store(value="v1", agent_id="a")
    await store.store(value="v2", agent_id="a")
    result = await store._preflight_check()
    assert result["ok"] is True
    assert result["checks"]["row_count"] == 2


@pytest.mark.asyncio
async def test_preflight_detects_missing_column(store):
    """Simulate schema drift by dropping a column and verify preflight catches it."""
    # Simulate drift: rebuild table missing `embedding`
    await store._db.execute("DROP TABLE memories")
    await store._db.execute(
        """
        CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            agent_id TEXT,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    await store._db.commit()

    result = await store._preflight_check()
    assert result["ok"] is False
    assert "embedding" in result["reason"]
    missing = result["checks"]["schema"]["missing_columns"]
    assert "embedding" in missing
    assert "content_hash" in missing


@pytest.mark.asyncio
async def test_preflight_reports_not_connected():
    s = LocalMemoryStore(db_path="/tmp/never-connected.db")
    result = await s._preflight_check()
    assert result["ok"] is False
    assert result["reason"] == "not_connected"


@pytest.mark.asyncio
async def test_health_check_backward_compat_shape(store):
    """Existing callers (HybridTradingMemoryClient) rely on {healthy: bool}."""
    result = await store.health_check()
    assert "healthy" in result
    assert result["healthy"] is True
    # New preflight block also available
    assert "preflight" in result
