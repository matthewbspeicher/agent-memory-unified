"""Unit tests for LocalMemoryStore."""

import pytest

from storage.memory import LocalMemoryStore


@pytest.fixture
async def memory_store(tmp_path):
    """Create an in-memory memory store for testing."""
    store = LocalMemoryStore(db_path=str(tmp_path / "test_memory.db"))
    await store.connect()
    yield store
    await store.close()


@pytest.fixture
async def memory_store_with_data(memory_store):
    """Create a memory store with some test data."""
    await memory_store.store(
        value="RSI indicator shows oversold conditions",
        visibility="private",
        agent_id="rsi_agent",
        key="rsi_oversold_2026",
        tags=["rsi", "oversold", "signal"],
        importance=8,
    )
    await memory_store.store(
        value="Moving average crossover detected - bullish signal",
        visibility="private",
        agent_id="ma_agent",
        key="ma_crossover_bullish",
        tags=["moving_average", "crossover", "bullish"],
        importance=7,
    )
    await memory_store.store(
        value="Market volatility increased significantly",
        visibility="public",
        agent_id="volatility_monitor",
        key="vol_spike_2026",
        tags=["volatility", "alert"],
        importance=9,
    )
    yield memory_store


class TestLocalMemoryStore:
    """Tests for LocalMemoryStore."""

    async def test_store_creates_memory(self, memory_store):
        """Test that storing a memory creates a record."""
        result = await memory_store.store(
            value="Test memory content",
            visibility="private",
            agent_id="test_agent",
        )

        assert result["id"] is not None
        assert result["value"] == "Test memory content"
        assert result["visibility"] == "private"

    async def test_get_retrieves_memory(self, memory_store):
        """Test retrieving a stored memory."""
        stored = await memory_store.store(
            value="Memory to retrieve",
            visibility="private",
            agent_id="test_agent",
            key="retrieve_test",
        )

        retrieved = await memory_store.get(stored["id"])
        assert retrieved is not None
        assert retrieved.value == "Memory to retrieve"
        assert retrieved.key == "retrieve_test"

    async def test_get_returns_none_for_missing(self, memory_store):
        """Test that getting a non-existent memory returns None."""
        result = await memory_store.get("non-existent-id")
        assert result is None

    async def test_list_returns_agent_memories(self, memory_store_with_data):
        """Test listing memories for a specific agent."""
        results = await memory_store_with_data.list(agent_id="rsi_agent")
        assert len(results) == 1
        assert results[0].agent_id == "rsi_agent"

    async def test_list_filters_by_visibility(self, memory_store_with_data):
        """Test listing memories filtered by visibility."""
        public_results = await memory_store_with_data.list(visibility="public")
        assert len(public_results) == 1
        assert public_results[0].visibility == "public"

        private_results = await memory_store_with_data.list(visibility="private")
        assert len(private_results) == 2

    async def test_search_finds_keyword(self, memory_store_with_data):
        """Test keyword search finds matching memories."""
        results = await memory_store_with_data.search(query="RSI")
        assert len(results) >= 1
        assert "RSI" in results[0]["value"]

    async def test_search_finds_in_summary(self, memory_store_with_data):
        """Test search finds matches in summary field."""
        # Store a memory with summary
        await memory_store_with_data.store(
            value="Some value",
            summary="This is a summary about volatility",
            visibility="private",
        )

        results = await memory_store_with_data.search(query="volatility")
        assert len(results) >= 1
        assert (
            "volatility" in results[0]["value"].lower()
            or "volatility" in (results[0].get("summary") or "").lower()
        )

    async def test_delete_removes_memory(self, memory_store):
        """Test deleting a memory removes it."""
        stored = await memory_store.store(
            value="Memory to delete",
            visibility="private",
        )

        deleted = await memory_store.delete(stored["id"])
        assert deleted is True

        # Verify it's gone
        result = await memory_store.get(stored["id"])
        assert result is None

    async def test_health_check_when_healthy(self, memory_store):
        """Test health check returns healthy when connected."""
        health = await memory_store.health_check()
        assert health["healthy"] is True

    async def test_health_check_when_not_connected(self):
        """Test health check returns unhealthy when not connected."""
        store = LocalMemoryStore(db_path="/nonexistent/path.db")
        health = await store.health_check()
        assert health["healthy"] is False
        assert "not_connected" in health["reason"]
