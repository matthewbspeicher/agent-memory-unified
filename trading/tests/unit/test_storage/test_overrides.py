import json

import aiosqlite
import pytest

from storage.db import init_db
from storage.overrides import AgentOverrideStore


@pytest.fixture
async def override_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield AgentOverrideStore(db)
    await db.close()


class TestAgentOverrideStore:
    async def test_get_returns_none_when_no_override(self, override_store):
        result = await override_store.get("nonexistent_agent")
        assert result is None

    async def test_set_and_get_trust_level(self, override_store):
        await override_store.set_trust_level("agent_1", "HIGH")
        override = await override_store.get("agent_1")
        assert override is not None
        assert override["agent_name"] == "agent_1"
        assert override["trust_level"] == "HIGH"

    async def test_set_and_get_runtime_parameters(self, override_store):
        params = {"max_position_size": 10000, "min_confidence": 0.75}
        await override_store.set_runtime_parameters("agent_2", params)
        override = await override_store.get("agent_2")
        assert override is not None
        assert override["agent_name"] == "agent_2"
        # Verify JSON round-trips correctly
        stored_params = json.loads(override["runtime_parameters"])
        assert stored_params == params
        assert stored_params["max_position_size"] == 10000
        assert stored_params["min_confidence"] == 0.75

    async def test_delete_override(self, override_store):
        await override_store.set_trust_level("agent_3", "MEDIUM")
        await override_store.delete("agent_3")
        result = await override_store.get("agent_3")
        assert result is None

    async def test_get_all_returns_empty_when_no_overrides(self, override_store):
        overrides = await override_store.get_all()
        assert overrides == []

    async def test_get_all_returns_all_overrides(self, override_store):
        await override_store.set_trust_level("agent_1", "HIGH")
        await override_store.set_runtime_parameters("agent_2", {"size": 100})
        overrides = await override_store.get_all()
        assert len(overrides) == 2
        agent_names = [o["agent_name"] for o in overrides]
        assert "agent_1" in agent_names
        assert "agent_2" in agent_names

    async def test_log_trust_change(self, override_store):
        await override_store.log_trust_change("agent_1", "LOW", "HIGH", "admin")
        history = await override_store.get_trust_history("agent_1")
        assert len(history) == 1
        assert history[0]["agent_name"] == "agent_1"
        assert history[0]["old_level"] == "LOW"
        assert history[0]["new_level"] == "HIGH"
        assert history[0]["changed_by"] == "admin"

    async def test_get_trust_history_empty(self, override_store):
        history = await override_store.get_trust_history("nonexistent_agent")
        assert history == []

    async def test_get_trust_history_multiple_events(self, override_store):
        await override_store.log_trust_change("agent_1", "LOW", "MEDIUM", "admin")
        await override_store.log_trust_change("agent_1", "MEDIUM", "HIGH", "system")
        history = await override_store.get_trust_history("agent_1", limit=10)
        assert len(history) == 2
        # Both transitions should be recorded
        new_levels = [h["new_level"] for h in history]
        assert "MEDIUM" in new_levels
        assert "HIGH" in new_levels

    async def test_upsert_trust_level(self, override_store):
        # Set initial trust level
        await override_store.set_trust_level("agent_1", "LOW")
        override = await override_store.get("agent_1")
        assert override["trust_level"] == "LOW"
        
        # Update trust level
        await override_store.set_trust_level("agent_1", "HIGH")
        override = await override_store.get("agent_1")
        assert override["trust_level"] == "HIGH"

    async def test_upsert_runtime_parameters(self, override_store):
        # Set initial parameters
        params1 = {"key1": "value1"}
        await override_store.set_runtime_parameters("agent_1", params1)
        override = await override_store.get("agent_1")
        stored_params = json.loads(override["runtime_parameters"])
        assert stored_params == params1
        
        # Update parameters
        params2 = {"key2": "value2"}
        await override_store.set_runtime_parameters("agent_1", params2)
        override = await override_store.get("agent_1")
        stored_params = json.loads(override["runtime_parameters"])
        assert stored_params == params2
