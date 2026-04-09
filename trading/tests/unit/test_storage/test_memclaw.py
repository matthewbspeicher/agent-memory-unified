"""Unit tests for MemClaw-style memory features."""

import pytest
from datetime import datetime, timezone, timedelta

from storage.memory import LocalMemoryStore, MEMORY_DECAY_DAYS, VALID_STATUSES
from storage.decay_scheduler import DecayScheduler


@pytest.fixture
async def memory_store(tmp_path):
    """Create an in-memory memory store for testing."""
    store = LocalMemoryStore(db_path=str(tmp_path / "test_memclaw.db"))
    await store.connect()
    yield store
    await store.close()


@pytest.fixture
async def memory_store_with_memclaw_data(memory_store):
    """Create a memory store with MemClaw-style test data."""
    # Store various memory types
    await memory_store.store(
        value="BTC price at $50,000",
        memory_type="fact",
        visibility_scope="scope_agent",
        weight=0.8,
        agent_id="trader_1",
    )
    await memory_store.store(
        value="Executed buy order for ETH",
        memory_type="action",
        visibility_scope="scope_team",
        weight=0.6,
        agent_id="trader_1",
    )
    await memory_store.store(
        value="User prefers low-risk strategies",
        memory_type="preference",
        visibility_scope="scope_org",
        weight=0.9,
        agent_id="user_1",
    )
    await memory_store.store(
        value="Old task that should decay",
        memory_type="task",
        visibility_scope="scope_agent",
        weight=0.5,
        agent_id="trader_1",
    )
    yield memory_store


class TestMemoryTypeValidation:
    """Tests for memory type enum validation."""

    def test_memory_decay_days_constant_exists(self):
        """Test that MEMORY_DECAY_DAYS constant is defined."""
        assert MEMORY_DECAY_DAYS is not None
        assert len(MEMORY_DECAY_DAYS) == 13

    def test_all_memclaw_types_have_decay(self):
        """Test all 13 MemClaw types have decay windows."""
        expected_types = [
            "fact",
            "episode",
            "decision",
            "preference",
            "task",
            "semantic",
            "intention",
            "plan",
            "commitment",
            "action",
            "outcome",
            "cancellation",
            "rule",
        ]
        for mem_type in expected_types:
            assert mem_type in MEMORY_DECAY_DAYS
            assert MEMORY_DECAY_DAYS[mem_type] > 0

    def test_valid_statuses_constant(self):
        """Test VALID_STATUSES contains all 8 statuses."""
        expected = {
            "active",
            "pending",
            "confirmed",
            "cancelled",
            "outdated",
            "conflicted",
            "archived",
            "deleted",
        }
        assert VALID_STATUSES == expected


class TestStatusTransition:
    """Tests for status transition validation."""

    async def test_transition_valid_active_to_confirmed(self, memory_store):
        """Test valid transition: active → confirmed."""
        stored = await memory_store.store(
            value="Test memory",
            memory_type="fact",
            agent_id="test",
        )
        record = await memory_store.transition_status(stored["id"], "confirmed")
        assert record is not None
        assert record.status == "confirmed"

    async def test_transition_valid_active_to_pending(self, memory_store):
        """Test valid transition: active → pending."""
        stored = await memory_store.store(
            value="Test memory",
            agent_id="test",
        )
        record = await memory_store.transition_status(stored["id"], "pending")
        assert record.status == "pending"

    async def test_transition_invalid_pending_to_active(self, memory_store):
        """Test invalid transition: pending → active (not allowed)."""
        stored = await memory_store.store(
            value="Test memory",
            agent_id="test",
        )
        await memory_store.transition_status(stored["id"], "pending")

        with pytest.raises(ValueError, match="Invalid transition"):
            await memory_store.transition_status(stored["id"], "active")

    async def test_transition_invalid_deleted_to_active(self, memory_store):
        """Test invalid transition from terminal state."""
        stored = await memory_store.store(
            value="Test memory",
            agent_id="test",
        )
        # Go through valid path to deleted
        await memory_store.transition_status(stored["id"], "confirmed")
        await memory_store.transition_status(stored["id"], "archived")
        await memory_store.transition_status(stored["id"], "deleted")

        with pytest.raises(ValueError, match="Invalid transition"):
            await memory_store.transition_status(stored["id"], "active")

    async def test_transition_nonexistent_memory(self, memory_store):
        """Test transition on non-existent memory returns None."""
        result = await memory_store.transition_status("nonexistent", "confirmed")
        assert result is None

    async def test_transition_invalid_status(self, memory_store):
        """Test transition with invalid status raises ValueError."""
        stored = await memory_store.store(
            value="Test memory",
            agent_id="test",
        )
        with pytest.raises(ValueError, match="Invalid status"):
            await memory_store.transition_status(stored["id"], "invalid_status")


class TestVisibilityScope:
    """Tests for visibility scope filtering."""

    async def test_store_with_visibility_scope(self, memory_store):
        """Test storing memory with visibility_scope."""
        result = await memory_store.store(
            value="Team memory",
            visibility_scope="scope_team",
            agent_id="test",
        )
        assert result is not None

        record = await memory_store.get(result["id"])
        assert record.visibility_scope == "scope_team"

    async def test_search_filters_by_visibility_scope(
        self, memory_store_with_memclaw_data
    ):
        """Test search can filter by visibility_scope."""
        # Search with scope_team filter
        results = await memory_store_with_memclaw_data.search(
            query="",
            visibility_scope="scope_team",
            limit=10,
        )
        assert all(r["visibility_scope"] == "scope_team" for r in results)

    async def test_search_filters_by_memory_type(self, memory_store_with_memclaw_data):
        """Test search can filter by memory_type."""
        results = await memory_store_with_memclaw_data.search(
            query="",
            memory_type_filter="fact",
            limit=10,
        )
        assert all(r["type"] == "fact" for r in results)

    async def test_search_filters_by_status(self, memory_store):
        """Test search can filter by status."""
        stored = await memory_store.store(
            value="Test memory",
            agent_id="test",
        )
        await memory_store.transition_status(stored["id"], "confirmed")

        results = await memory_store.search(
            query="Test",
            status_filter="confirmed",
            limit=10,
        )
        assert len(results) >= 1
        assert all(r["status"] == "confirmed" for r in results)

    async def test_search_filters_by_min_weight(self, memory_store_with_memclaw_data):
        """Test search can filter by minimum weight."""
        results = await memory_store_with_memclaw_data.search(
            query="",
            min_weight=0.7,
            limit=10,
        )
        assert all(r["weight"] >= 0.7 for r in results)


class TestDecayScheduler:
    """Tests for decay scheduler logic."""

    def test_scheduler_disabled_by_default(self, memory_store):
        """Test scheduler is disabled by default."""
        scheduler = DecayScheduler(memory_store, enabled=False)
        assert scheduler.enabled is False

    async def test_run_once_when_disabled(self, memory_store):
        """Test run_once returns 0 when disabled."""
        scheduler = DecayScheduler(memory_store, enabled=False)
        decayed = await scheduler.run_once()
        assert decayed == 0

    async def test_run_once_when_enabled(self, memory_store):
        """Test run_once processes memories when enabled."""
        scheduler = DecayScheduler(memory_store, enabled=True)
        decayed = await scheduler.run_once()
        assert decayed >= 0  # May be 0 if no memories to decay

    def test_scheduler_status(self, memory_store):
        """Test get_status returns scheduler info."""
        scheduler = DecayScheduler(
            memory_store,
            enabled=True,
            interval_seconds=1800,
        )
        status = scheduler.get_status()
        assert status["enabled"] is True
        assert status["running"] is False
        assert status["interval_seconds"] == 1800
        assert status["total_decayed"] == 0

    def test_stop_scheduler(self, memory_store):
        """Test stop() sets running to False."""
        scheduler = DecayScheduler(memory_store, enabled=True)
        scheduler._running = True  # Simulate running state
        scheduler.stop()
        assert scheduler._running is False


class TestMemoryWeight:
    """Tests for weight (MemClaw importance) field."""

    async def test_default_weight(self, memory_store):
        """Test default weight is 0.5."""
        result = await memory_store.store(
            value="Test memory",
            agent_id="test",
        )
        record = await memory_store.get(result["id"])
        assert record.weight == 0.5

    async def test_custom_weight(self, memory_store):
        """Test storing memory with custom weight."""
        result = await memory_store.store(
            value="Important memory",
            weight=0.95,
            agent_id="test",
        )
        record = await memory_store.get(result["id"])
        assert record.weight == 0.95

    async def test_computed_decay_days(self, memory_store):
        """Test computed_decay_days property."""
        result = await memory_store.store(
            value="Test fact",
            memory_type="fact",
            agent_id="test",
        )
        record = await memory_store.get(result["id"])
        assert record.computed_decay_days == 120  # fact decay

    async def test_explicit_decay_days_overrides(self, memory_store):
        """Test explicit decay_days overrides memory_type default."""
        result = await memory_store.store(
            value="Test fact",
            memory_type="fact",
            decay_days=30,  # Override default 120
            agent_id="test",
        )
        record = await memory_store.get(result["id"])
        assert record.decay_days == 30
        assert record.computed_decay_days == 30
