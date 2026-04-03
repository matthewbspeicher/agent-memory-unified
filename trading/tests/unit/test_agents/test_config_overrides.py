# tests/unit/test_agents/test_config_overrides.py
import json
import pytest
import aiosqlite

from agents.config import apply_overrides
from agents.models import AgentConfig, ActionLevel, TrustLevel
from storage.db import init_db
from storage.agent_registry import AgentStore


@pytest.fixture
async def agent_store():
    """Create an in-memory SQLite DB with agent_registry table."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield AgentStore(db)
    await db.close()


@pytest.fixture
def base_config():
    """Create a base agent config for testing."""
    return AgentConfig(
        name="test-agent",
        strategy="rsi",
        schedule="continuous",
        action_level=ActionLevel.NOTIFY,
        interval=60,
        universe=["AAPL", "MSFT"],
        parameters={"period": 14, "oversold": 30},
        trust_level=TrustLevel.MONITORED,
    )


class TestApplyOverrides:
    async def test_apply_overrides_trust_level(self, base_config, agent_store):
        """Test that trust_level from DB entry is applied to config."""
        # Create agent then update trust level
        await agent_store.create({"name": "test-agent", "strategy": "rsi"})
        await agent_store.update("test-agent", trust_level="autonomous")
        
        # Apply overrides
        result = await apply_overrides(base_config, agent_store)
        
        # Verify trust level was updated
        assert result.trust_level == TrustLevel.AUTONOMOUS
        assert result.name == "test-agent"
        assert result.strategy == "rsi"

    async def test_apply_overrides_runtime_parameters(self, base_config, agent_store):
        """Test that runtime_overrides from DB entry are applied to config."""
        params = {"max_position_size": 10000, "min_confidence": 0.75}
        await agent_store.create({
            "name": "test-agent",
            "strategy": "rsi",
            "runtime_overrides": params,
        })
        
        # Apply overrides
        result = await apply_overrides(base_config, agent_store)
        
        # Verify runtime_overrides were merged
        assert result.runtime_overrides == params
        assert result.runtime_overrides["max_position_size"] == 10000
        assert result.runtime_overrides["min_confidence"] == 0.75

    async def test_apply_overrides_no_override(self, base_config, agent_store):
        """Test that config is unchanged when no DB entry exists."""
        # Apply overrides with no entry in DB
        result = await apply_overrides(base_config, agent_store)
        
        # Verify config unchanged
        assert result.trust_level == TrustLevel.MONITORED
        assert result.runtime_overrides == {}
        assert result.name == "test-agent"
        assert result.strategy == "rsi"

    async def test_apply_overrides_both_fields(self, base_config, agent_store):
        """Test that both trust_level and runtime_overrides can be applied together."""
        params = {"threshold": 0.8}
        await agent_store.create({
            "name": "test-agent",
            "strategy": "rsi",
            "trust_level": "assisted",
            "runtime_overrides": params,
        })
        
        # Apply overrides
        result = await apply_overrides(base_config, agent_store)
        
        # Verify both were applied
        assert result.trust_level == TrustLevel.ASSISTED
        assert result.runtime_overrides == params

    async def test_apply_overrides_different_agent(self, base_config, agent_store):
        """Test that overrides for different agent don't affect this config."""
        # Create entry for different agent
        await agent_store.create({
            "name": "other-agent",
            "strategy": "rsi",
            "trust_level": "autonomous",
        })
        
        # Apply overrides to test-agent
        result = await apply_overrides(base_config, agent_store)
        
        # Verify test-agent config unchanged
        assert result.trust_level == TrustLevel.MONITORED

    async def test_apply_overrides_empty_runtime_overrides(self, base_config, agent_store):
        """Test handling of empty runtime overrides."""
        await agent_store.create({
            "name": "test-agent",
            "strategy": "rsi",
            "runtime_overrides": {},
        })
        
        # Apply overrides
        result = await apply_overrides(base_config, agent_store)
        
        # Verify empty dict is set (no-op since no truthy overrides)
        assert result.runtime_overrides == {}
