"""Integration test: agent YAML exit_rules are attached to ExitManager after fill."""

from __future__ import annotations

from decimal import Decimal
import pytest

from agents.models import Opportunity
from broker.models import Symbol, AssetType, OrderSide, LimitOrder
from exits.rules import PreExpiryExit, ProbabilityTrailingStop, PartialExitRule


def _make_opportunity(agent_name: str = "kalshi_daily") -> Opportunity:
    from datetime import datetime, timezone
    import uuid

    sym = Symbol(ticker="KXBTCD-25MAR28", asset_type=AssetType.PREDICTION)
    return Opportunity(
        id=str(uuid.uuid4()),
        agent_name=agent_name,
        symbol=sym,
        signal="buy",
        confidence=0.8,
        reasoning="test",
        data={},
        timestamp=datetime.now(timezone.utc),
        suggested_trade=LimitOrder(
            symbol=sym,
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id="KALSHI_PAPER",
            limit_price=Decimal("0.60"),
        ),
        broker_id="kalshi_paper",
    )


@pytest.fixture
def exit_manager():
    from exits.manager import ExitManager

    return ExitManager()


@pytest.mark.asyncio
async def test_yaml_exit_rules_attached_after_fill(exit_manager):
    """When agent has exit_rules in config, those rules should be attached post-fill."""
    from datetime import datetime, timezone, timedelta
    from agents.config import AgentConfigSchema
    from exits.rules import parse_rule

    exit_rules_cfg = [
        {
            "type": "pre_expiry_exit",
            "hours_before_expiry": 2.0,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(hours=10)
            ).isoformat(),
        },
        {"type": "probability_trailing_stop", "trail_pp": 20.0},
        {"type": "partial_exit", "target_price": "0.80", "fraction": 0.5},
    ]

    # Validate config schema round-trip
    schema = AgentConfigSchema(
        name="kalshi_daily",
        strategy="kalshi_news_arb",  # must be registered
        action_level="auto_execute",
        schedule="continuous",
        exit_rules=exit_rules_cfg,
    )
    assert len(schema.exit_rules) == 3

    # Parse rules and verify types
    parsed = [parse_rule(d) for d in exit_rules_cfg]
    assert isinstance(parsed[0], PreExpiryExit)
    assert isinstance(parsed[1], ProbabilityTrailingStop)
    assert isinstance(parsed[2], PartialExitRule)
    assert parsed[1].trail_pp == 20.0
    assert parsed[2].fraction == 0.5

    # Attach to exit manager and confirm they are retrievable
    await exit_manager.attach(position_id=1, rules=[r for r in parsed if r])
    triggered = exit_manager.check(1, Decimal("0.50"))
    # None of these should trigger yet (price 0.50, no trailing peak, not in expiry window)
    assert triggered is None


@pytest.mark.asyncio
async def test_yaml_exit_rules_validator_rejects_unknown_type():
    """AgentConfigSchema should reject unknown exit rule types."""
    from pydantic import ValidationError
    from agents.config import AgentConfigSchema

    with pytest.raises(ValidationError):
        AgentConfigSchema(
            name="test_agent",
            strategy="rsi",
            exit_rules=[{"type": "unknown_rule_type"}],
        )
