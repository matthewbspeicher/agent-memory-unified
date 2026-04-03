from datetime import datetime, timedelta
from typing import Any

from agents.models import (
    ActionLevel,
    AgentConfig,
    AgentInfo,
    AgentStatus,
    Opportunity,
    OpportunityStatus,
    TrustLevel,
)
from broker.models import Symbol


class TestActionLevel:
    def test_values(self):
        assert ActionLevel.NOTIFY == "notify"
        assert ActionLevel.SUGGEST_TRADE == "suggest_trade"
        assert ActionLevel.AUTO_EXECUTE == "auto_execute"


class TestOpportunityStatus:
    def test_values(self):
        assert OpportunityStatus.PENDING == "pending"
        assert OpportunityStatus.APPROVED == "approved"
        assert OpportunityStatus.REJECTED == "rejected"
        assert OpportunityStatus.EXECUTED == "executed"
        assert OpportunityStatus.EXPIRED == "expired"


class TestTrustLevel:
    def test_trust_level_enum(self):
        assert TrustLevel.MONITORED == "monitored"
        assert TrustLevel.ASSISTED == "assisted"
        assert TrustLevel.AUTONOMOUS == "autonomous"


class TestAgentConfig:
    def test_minimal_config(self):
        cfg = AgentConfig(
            name="test",
            strategy="rsi",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
        )
        assert cfg.name == "test"
        assert cfg.interval == 60
        assert cfg.parameters == {}
        assert cfg.shadow_mode is False

    def test_agent_config_trust_defaults_to_monitored(self):
        cfg = AgentConfig(
            name="test",
            strategy="rsi",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
        )
        assert cfg.trust_level == TrustLevel.MONITORED
        assert cfg.parameter_bounds == {}
        assert cfg.optimization == {}

    def test_full_config(self):
        cfg = AgentConfig(
            name="rsi-sp500",
            strategy="rsi",
            schedule="continuous",
            action_level=ActionLevel.SUGGEST_TRADE,
            interval=30,
            universe="SP500",
            parameters={"period": 14, "oversold": 30},
            shadow_mode=True,
        )
        assert cfg.universe == "SP500"
        assert cfg.parameters["period"] == 14
        assert cfg.shadow_mode is True

    def test_agent_config_shadow_mode_default(self):
        config = AgentConfig(
            name="test",
            strategy="rsi",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
        )
        assert config.shadow_mode is False

    def test_agent_config_shadow_mode_true(self):
        config = AgentConfig(
            name="test",
            strategy="rsi",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
            shadow_mode=True,
        )
        assert config.shadow_mode is True

    def test_agent_config_promotion_criteria(self):
        criteria: dict[str, Any] = {"min_cycles": 50, "sharpe_threshold": 1.0}
        config = AgentConfig(
            name="test",
            strategy="rsi",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
            promotion_criteria=criteria,
        )
        assert config.promotion_criteria == criteria


class TestOpportunity:
    def test_create_opportunity(self):
        opp = Opportunity(
            id="test-123",
            agent_name="rsi-agent",
            symbol=Symbol(ticker="AAPL"),
            signal="RSI_OVERSOLD",
            confidence=0.85,
            reasoning="RSI at 25",
            data={"rsi": 25.0},
            timestamp=datetime.now(),
        )
        assert opp.status == OpportunityStatus.PENDING
        assert opp.suggested_trade is None
        assert opp.confidence == 0.85

    def test_opportunity_with_expiry(self):
        now = datetime.now()
        opp = Opportunity(
            id="test-456",
            agent_name="vol-agent",
            symbol=Symbol(ticker="TSLA"),
            signal="VOLUME_SPIKE",
            confidence=0.7,
            reasoning="2.5x average volume",
            data={"volume_ratio": 2.5},
            timestamp=now,
            expires_at=now + timedelta(hours=6),
        )
        assert opp.expires_at > now


class TestAgentInfo:
    def test_default_state(self):
        cfg = AgentConfig(
            name="test",
            strategy="rsi",
            schedule="on_demand",
            action_level=ActionLevel.NOTIFY,
        )
        info = AgentInfo(
            name="test",
            description="Test agent",
            status=AgentStatus.STOPPED,
            config=cfg,
        )
        assert info.last_run is None
        assert info.error_count == 0
