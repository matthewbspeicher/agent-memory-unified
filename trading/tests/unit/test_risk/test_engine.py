# tests/unit/test_risk/test_engine.py
from decimal import Decimal
from unittest.mock import MagicMock
import pytest

from broker.models import AccountBalance, MarketOrder, OrderSide, Quote, Symbol
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.rules import MaxPositionSize, MaxDailyLoss, PortfolioContext, RiskResult


def _ctx():
    return PortfolioContext(
        positions=[], balance=AccountBalance(
            account_id="U123", net_liquidation=Decimal("100000"),
            buying_power=Decimal("50000"), cash=Decimal("30000"),
            maintenance_margin=Decimal("20000"),
        ),
    )


def _trade():
    return MarketOrder(
        symbol=Symbol(ticker="AAPL"), side=OrderSide.BUY,
        quantity=Decimal("10"), account_id="U123",
    ), Quote(symbol=Symbol(ticker="AAPL"), last=Decimal("150"))


class TestRiskEngine:
    @pytest.mark.asyncio
    async def test_all_rules_pass(self):
        ks = KillSwitch()
        engine = RiskEngine(
            rules=[MaxPositionSize(max_dollars=5000, max_shares=500)],
            kill_switch=ks,
        )
        trade, quote = _trade()
        result = await engine.evaluate(trade, quote, _ctx())
        assert result.passed

    @pytest.mark.asyncio
    async def test_rule_fails(self):
        ks = KillSwitch()
        engine = RiskEngine(
            rules=[MaxPositionSize(max_dollars=100, max_shares=500)],
            kill_switch=ks,
        )
        trade, quote = _trade()  # $1500 > $100
        result = await engine.evaluate(trade, quote, _ctx())
        assert not result.passed

    @pytest.mark.asyncio
    async def test_kill_switch_blocks(self):
        ks = KillSwitch()
        ks.enable("manual")
        engine = RiskEngine(rules=[], kill_switch=ks)
        trade, quote = _trade()
        result = await engine.evaluate(trade, quote, _ctx())
        assert not result.passed

    @pytest.mark.asyncio
    async def test_max_daily_loss_triggers_kill_switch(self):
        ks = KillSwitch()
        rule = MaxDailyLoss(max_dollars=1000, action="kill_switch")
        engine = RiskEngine(rules=[rule], kill_switch=ks)
        trade, quote = _trade()
        ctx = _ctx()
        ctx.daily_pnl = Decimal("-1200")
        result = await engine.evaluate(trade, quote, ctx)
        assert not result.passed
        assert not result.passed
        assert ks.is_enabled  # kill switch auto-triggered
