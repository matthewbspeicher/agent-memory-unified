import pytest
from unittest.mock import MagicMock
from risk.engine import RiskEngine

@pytest.mark.asyncio
async def test_three_tier_evaluation():
    ks = MagicMock()
    ks.is_enabled = False
    engine = RiskEngine(rules=[], kill_switch=ks)
    trade_mock = MagicMock()
    portfolio_mock = MagicMock()
    
    # Check that engine has the new specialized evaluation methods
    # (Existing evaluate handles order level by default)
    result = await engine.evaluate_order(trade_mock, MagicMock(), MagicMock())
    assert result.passed
    
    # Portfolio level checks (e.g. total exposure)
    port_result = await engine.evaluate_portfolio(portfolio_mock)
    assert port_result is True
    
    # Strategy level checks (e.g. max consecutive losses)
    strat_result = await engine.evaluate_strategy("test_agent", {})
    assert strat_result is True
