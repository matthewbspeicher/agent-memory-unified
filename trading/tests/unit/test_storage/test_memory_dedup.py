"""Unit tests for LocalMemoryStore content-hash dedup + WAL."""

import asyncio
import hashlib

import pytest

from storage.memory import LocalMemoryStore


@pytest.fixture
async def memory_store(tmp_path):
    """Create a memory store for testing."""
    store = LocalMemoryStore(db_path=str(tmp_path / "test_dedup.db"))
    await store.connect()
    yield store
    await store.close()


class TestWALAndBusyTimeout:
    """Tests for WAL journal mode and busy_timeout pragma."""

    async def test_wal_mode_enabled(self, memory_store):
        """WAL journal mode should be enabled after connect."""
        cursor = await memory_store._db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0] == "wal"

    async def test_busy_timeout_set(self, memory_store):
        """busy_timeout should be 5000ms after connect."""
        cursor = await memory_store._db.execute("PRAGMA busy_timeout")
        row = await cursor.fetchone()
        assert row[0] == 5000


class TestContentHashDedup:
    """Tests for content-hash deduplication in store()."""

    async def test_store_adds_content_hash(self, memory_store):
        """store() should populate content_hash (32-char MD5 hex)."""
        result = await memory_store.store(
            value="unique content for hashing",
            visibility="private",
        )
        record = await memory_store.get(result["id"])
        assert record is not None

        # Verify hash is stored in the DB row
        cursor = await memory_store._db.execute(
            "SELECT content_hash FROM memories WHERE id = ?", (result["id"],)
        )
        row = await cursor.fetchone()
        expected_hash = hashlib.md5("unique content for hashing".encode()).hexdigest()
        assert row[0] == expected_hash
        assert len(row[0]) == 32

    async def test_duplicate_store_returns_same_id(self, memory_store):
        """Storing identical content should return same ID with deduplicated flag."""
        first = await memory_store.store(
            value="duplicate me",
            visibility="private",
            agent_id="agent_a",
        )
        second = await memory_store.store(
            value="duplicate me",
            visibility="private",
            agent_id="agent_b",
        )

        assert second["id"] == first["id"]
        assert second["deduplicated"] is True

    async def test_duplicate_increments_access_count(self, memory_store):
        """Duplicate store should increment access_count."""
        first = await memory_store.store(
            value="count me",
            visibility="private",
        )

        # Store same content again
        await memory_store.store(value="count me", visibility="private")

        record = await memory_store.get(first["id"])
        assert record is not None
        assert record.access_count == 1  # 0 initial + 1 increment

    async def test_different_content_gets_different_ids(self, memory_store):
        """Different content should produce different memory IDs."""
        first = await memory_store.store(value="content A", visibility="private")
        second = await memory_store.store(value="content B", visibility="private")

        assert first["id"] != second["id"]
        assert "deduplicated" not in first or first.get("deduplicated") is not True
        assert "deduplicated" not in second or second.get("deduplicated") is not True


class TestCheckDuplicate:
    """Tests for check_duplicate() method."""

    async def test_check_duplicate_finds_existing(self, memory_store):
        """check_duplicate() should return record when content exists."""
        stored = await memory_store.store(
            value="find me later",
            visibility="private",
            agent_id="test_agent",
        )

        dup = await memory_store.check_duplicate("find me later")
        assert dup is not None
        assert dup.id == stored["id"]
        assert dup.value == "find me later"

    async def test_check_duplicate_returns_none(self, memory_store):
        """check_duplicate() should return None when content doesn't exist."""
        result = await memory_store.check_duplicate("nonexistent content")
        assert result is None

    async def test_check_duplicate_not_connected_raises(self):
        """check_duplicate() should raise RuntimeError when not connected."""
        store = LocalMemoryStore(db_path="/tmp/not_connected.db")
        with pytest.raises(RuntimeError, match="Not connected"):
            await store.check_duplicate("anything")


class TestConcurrentDuplicates:
    """Tests for concurrent duplicate stores."""

    async def test_concurrent_duplicate_stores_no_crash(self, tmp_path):
        """Multiple concurrent stores of the same content should not crash."""
        store = LocalMemoryStore(db_path=str(tmp_path / "concurrent.db"))
        await store.connect()
        try:
            tasks = [
                store.store(value="concurrent content", visibility="private")
                for _ in range(5)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # No exceptions should have been raised
            for r in results:
                assert not isinstance(r, Exception), f"Got exception: {r}"

            # All results should reference the same ID
            ids = {r["id"] for r in results}
            assert len(ids) == 1
        finally:
            await store.close()
