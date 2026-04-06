# tests/unit/test_agents/test_config.py
import yaml

from agents.config import AgentConfigSchema, load_agents_config
from agents.models import ActionLevel, TrustLevel


class TestLoadAgentsConfig:
    def test_agent_config_schema_defaults_shadow_mode_to_false(self):
        config = AgentConfigSchema(name="rsi-test", strategy="rsi")

        assert config.shadow_mode is False

    def test_load_rsi_agent(self, tmp_path):
        config = {
            "agents": [
                {
                    "name": "rsi-test",
                    "strategy": "rsi",
                    "schedule": "continuous",
                    "interval": 60,
                    "action_level": "suggest_trade",
                    "universe": "SP500",
                    "parameters": {"period": 14, "oversold": 30, "overbought": 70},
                }
            ]
        }
        path = tmp_path / "agents.yaml"
        path.write_text(yaml.dump(config))

        agents = load_agents_config(str(path))
        assert len(agents) == 1
        assert agents[0].name == "rsi-test"
        assert agents[0].config.action_level == ActionLevel.SUGGEST_TRADE
        assert agents[0].config.shadow_mode is False

    def test_load_agents_config_maps_shadow_mode(self, tmp_path):
        config = {
            "agents": [
                {
                    "name": "rsi-shadow",
                    "strategy": "rsi",
                    "schedule": "continuous",
                    "interval": 60,
                    "action_level": "suggest_trade",
                    "shadow_mode": True,
                    "universe": "SP500",
                }
            ]
        }
        path = tmp_path / "agents.yaml"
        path.write_text(yaml.dump(config))

        agents = load_agents_config(str(path))

        assert len(agents) == 1
        assert agents[0].config.shadow_mode is True

    def test_load_agents_config_maps_trust_level(self, tmp_path):
        config = {
            "agents": [
                {
                    "name": "rsi-assisted",
                    "strategy": "rsi",
                    "schedule": "continuous",
                    "interval": 60,
                    "action_level": "suggest_trade",
                    "trust_level": "assisted",
                    "universe": "SP500",
                }
            ]
        }
        path = tmp_path / "agents.yaml"
        path.write_text(yaml.dump(config))

        agents = load_agents_config(str(path))

        assert len(agents) == 1
        assert agents[0].config.trust_level == TrustLevel.ASSISTED

    def test_load_llm_agent(self, tmp_path):
        config = {
            "agents": [
                {
                    "name": "ai-test",
                    "strategy": "llm",
                    "schedule": "cron",
                    "cron": "0 16 * * 1-5",
                    "action_level": "suggest_trade",
                    "model": "claude-sonnet-4-6",
                    "system_prompt": "Analyze markets",
                    "universe": "SP500",
                }
            ]
        }
        path = tmp_path / "agents.yaml"
        path.write_text(yaml.dump(config))

        agents = load_agents_config(str(path))
        assert len(agents) == 1
        assert agents[0].name == "ai-test"

    def test_empty_config(self, tmp_path):
        path = tmp_path / "agents.yaml"
        path.write_text(yaml.dump({"agents": []}))
        agents = load_agents_config(str(path))
        assert agents == []
