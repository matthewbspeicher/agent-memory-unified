"""Unit tests for AgentStore (agent_registry table)."""

from __future__ import annotations

import aiosqlite
import pytest

from storage.db import init_db
from storage.agent_registry import AgentStore


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield AgentStore(db)
    await db.close()


def _agent_entry(
    name: str = "rsi_agent",
    strategy: str = "rsi",
    **overrides,
) -> dict:
    entry = {
        "name": name,
        "strategy": strategy,
        "schedule": "continuous",
        "interval_or_cron": 60,
        "universe": ["AAPL", "MSFT"],
        "parameters": {"rsi_threshold": 30, "lookback_period": 14},
        "status": "active",
        "trust_level": "monitored",
        "runtime_overrides": {},
        "created_by": "human",
        "parent_name": None,
        "generation": 1,
        "creation_context": {},
    }
    entry.update(overrides)
    return entry


class TestAgentStoreCreate:
    async def test_create_agent(self, store: AgentStore):
        entry = _agent_entry()
        created = await store.create(entry)
        assert created["name"] == "rsi_agent"
        assert created["strategy"] == "rsi"
        assert created["universe"] == ["AAPL", "MSFT"]
        assert created["parameters"] == {"rsi_threshold": 30, "lookback_period": 14}

    async def test_create_duplicate_name_raises(self, store: AgentStore):
        entry = _agent_entry()
        await store.create(entry)
        with pytest.raises(Exception):
            await store.create(entry)

    async def test_create_hermes_agent(self, store: AgentStore):
        entry = _agent_entry(
            name="rsi_evolved",
            created_by="hermes",
            parent_name="rsi_agent",
            generation=2,
            creation_context={"reason": "volatility spike"},
        )
        created = await store.create(entry)
        assert created["created_by"] == "hermes"
        assert created["parent_name"] == "rsi_agent"
        assert created["generation"] == 2


class TestAgentStoreGet:
    async def test_get_by_name(self, store: AgentStore):
        await store.create(_agent_entry())
        agent = await store.get("rsi_agent")
        assert agent is not None
        assert agent["name"] == "rsi_agent"

    async def test_get_nonexistent_returns_none(self, store: AgentStore):
        agent = await store.get("nonexistent")
        assert agent is None

    async def test_get_all_active(self, store: AgentStore):
        await store.create(_agent_entry("agent_a"))
        await store.create(_agent_entry("agent_b", status="dormant"))
        active = await store.get_all_active()
        assert len(active) == 1
        assert active[0]["name"] == "agent_a"


class TestAgentStoreUpdate:
    async def test_update_status(self, store: AgentStore):
        await store.create(_agent_entry())
        await store.update("rsi_agent", {"status": "dormant"})
        agent = await store.get("rsi_agent")
        assert agent["status"] == "dormant"

    async def test_update_parameters(self, store: AgentStore):
        await store.create(_agent_entry())
        await store.update("rsi_agent", {"parameters": {"rsi_threshold": 25}})
        agent = await store.get("rsi_agent")
        assert agent["parameters"] == {"rsi_threshold": 25}

    async def test_update_trust_level(self, store: AgentStore):
        await store.create(_agent_entry())
        await store.update("rsi_agent", {"trust_level": "trusted"})
        agent = await store.get("rsi_agent")
        assert agent["trust_level"] == "trusted"


class TestAgentStoreList:
    async def test_list_all(self, store: AgentStore):
        await store.create(_agent_entry("agent_a"))
        await store.create(_agent_entry("agent_b"))
        agents = await store.list_all()
        assert len(agents) == 2
        names = {a["name"] for a in agents}
        assert names == {"agent_a", "agent_b"}

    async def test_list_by_status(self, store: AgentStore):
        await store.create(_agent_entry("agent_a", status="active"))
        await store.create(_agent_entry("agent_b", status="dormant"))
        active = await store.list_by_status("active")
        assert len(active) == 1
        assert active[0]["name"] == "agent_a"


class TestAgentStoreCreateEvolved:
    """Test create_evolved_agent method (Hermes spawning with safety defaults)."""

    async def test_evolved_agent_defaults_shadow_mode_true(self, store: AgentStore):
        """Safety: evolved agents must have shadow_mode=True by default."""
        await store.create(_agent_entry("parent_rsi", strategy="rsi"))
        evolved = await store.create_evolved_agent(
            name="parent_rsi_gen2",
            strategy="rsi",
            parent_name="parent_rsi",
            parameters={"rsi_threshold": 25},
        )
        assert evolved["shadow_mode"] == True  # noqa: E712
        assert evolved["created_by"] == "hermes"
        assert evolved["parent_name"] == "parent_rsi"
        assert evolved["generation"] == 2

    async def test_evolved_agent_increments_generation(self, store: AgentStore):
        await store.create(_agent_entry("gen1_agent", generation=1))
        gen2 = await store.create_evolved_agent(
            name="gen2_agent", strategy="rsi", parent_name="gen1_agent"
        )
        assert gen2["generation"] == 2

        gen3 = await store.create_evolved_agent(
            name="gen3_agent", strategy="rsi", parent_name="gen2_agent"
        )
        assert gen3["generation"] == 3


class TestAgentStoreSeedFromYAML:
    async def test_seed_from_yaml_populates_table(self, store: AgentStore):
        yaml_agents = [
            {
                "name": "rsi_alpha",
                "strategy": "rsi",
                "schedule": "continuous",
                "interval": 60,
                "universe": ["AAPL"],
                "parameters": {"rsi_threshold": 30},
            },
            {
                "name": "volume_beta",
                "strategy": "volume_spike",
                "schedule": "continuous",
                "interval": 120,
                "universe": ["MSFT", "GOOG"],
                "parameters": {"volume_mult": 2.0},
            },
        ]
        count = await store.seed_from_yaml(yaml_agents)
        assert count == 2
        agents = await store.list_all()
        assert len(agents) == 2

    async def test_seed_from_yaml_idempotent(self, store: AgentStore):
        yaml_agents = [{"name": "rsi", "strategy": "rsi", "interval": 60}]
        await store.seed_from_yaml(yaml_agents)
        count = await store.seed_from_yaml(yaml_agents)
        assert count == 0  # no new agents added
        agents = await store.list_all()
        assert len(agents) == 1

    async def test_seed_from_yaml_respects_explicit_shadow_mode(
        self, store: AgentStore
    ):
        """YAML agents can explicitly set shadow_mode."""
        yaml_agents = [
            {
                "name": "shadow_agent",
                "strategy": "rsi",
                "interval": 60,
                "shadow_mode": True,
            }
        ]
        await store.seed_from_yaml(yaml_agents)
        agent = await store.get("shadow_agent")
        assert agent["shadow_mode"] == True  # noqa: E712
