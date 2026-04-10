import pytest
from trading.competition.escape_rooms.infinite_city import InfiniteCityEnvironment

class TestInfiniteCityInitialization:
    def test_city_init(self):
        env = InfiniteCityEnvironment({"grid_size": 10})
        assert env.grid_size == 10
        assert "Energy" in env.global_resources
        assert env.state == "ACTIVE"
        assert env.cycle_count == 0

class TestInfiniteCityInfrastructure:
    @pytest.mark.asyncio
    async def test_upgrade_infrastructure(self):
        env = InfiniteCityEnvironment()
        initial_budget = env.global_resources["Budget"]
        initial_energy = env.global_resources["Energy"]
        
        res = await env.execute_tool("upgrade_infrastructure", {
            "resource_type": "Energy",
            "cost": 500
        })
        
        assert "successfully" in res
        assert env.global_resources["Budget"] == initial_budget - 500
        assert env.global_resources["Energy"] == initial_energy + 200

    @pytest.mark.asyncio
    async def test_upgrade_insufficient_funds(self):
        env = InfiniteCityEnvironment()
        res = await env.execute_tool("upgrade_infrastructure", {
            "resource_type": "Water",
            "cost": 6000 # Budget is 5000
        })
        assert "Error: Insufficient Budget" in res

class TestInfiniteCityGovernanceAndCycle:
    @pytest.mark.asyncio
    async def test_governance_policy_effects(self):
        env = InfiniteCityEnvironment()
        initial_sentiment = env.global_resources["Public_Sentiment"]
        
        res = await env.execute_tool("enact_policy", {
            "policy_text": "Implement energy conservation protocol",
            "target_metric": "Energy_Conservation"
        })
        
        assert "Policy enacted" in res
        assert env.global_resources["Public_Sentiment"] == initial_sentiment - 10
        assert len(env.active_policies) == 1
        
        # Test cycle drain with policy
        initial_energy = env.global_resources["Energy"]
        env.advance_cycle()
        
        # Drain should be 25 with policy, not 50
        assert env.global_resources["Energy"] == initial_energy - 25

    def test_systemic_collapse(self):
        env = InfiniteCityEnvironment()
        env.global_resources["Energy"] = 40 # Set low to trigger collapse on next cycle

        env.advance_cycle() # Drains 50

        assert env.state == "COLLAPSED"
        assert env.winner == "COLLAPSE"
        assert "Systemic Collapse" in env.match_log[-1]


class TestInfiniteCityPublicInterface:
    @pytest.mark.asyncio
    async def test_advance_cycle_via_execute_tool(self):
        env = InfiniteCityEnvironment({"survival_target": 3})
        assert env.cycle_count == 0
        res = await env.execute_tool("advance_cycle", {"agent_id": 0})
        assert "Cycle 1" in res
        assert env.cycle_count == 1

    @pytest.mark.asyncio
    async def test_survival_target_wins(self):
        env = InfiniteCityEnvironment({"survival_target": 2})
        # Protect against resource drain by inflating resources
        env.global_resources["Energy"] = 10_000
        env.global_resources["Water"] = 10_000
        await env.execute_tool("advance_cycle", {"agent_id": 0})
        await env.execute_tool("advance_cycle", {"agent_id": 0})
        assert env.state == "SURVIVED"
        assert env.winner == "AGENT"
        assert env.verify_flag("AGENT") is True
        assert env.verify_flag("COLLAPSE") is False

    @pytest.mark.asyncio
    async def test_advance_cycle_stops_after_collapse(self):
        env = InfiniteCityEnvironment()
        env.global_resources["Energy"] = 40
        env.global_resources["Water"] = 40
        await env.execute_tool("advance_cycle", {"agent_id": 0})  # → COLLAPSED
        assert env.state == "COLLAPSED"
        cycle_after_collapse = env.cycle_count
        # Another advance should be a no-op
        await env.execute_tool("advance_cycle", {"agent_id": 0})
        assert env.cycle_count == cycle_after_collapse