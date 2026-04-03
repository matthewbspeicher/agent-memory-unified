import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agents.models import ActionLevel, Opportunity, OpportunityStatus
from broker.models import OrderSide, Symbol, MarketOrder
from agents.router import ConsensusRouter, OpportunityRouter

class StubRouter:
    def __init__(self):
        self.routes = []
        
    async def route(self, opportunity: Opportunity, action_level: ActionLevel) -> None:
        self.routes.append((opportunity, action_level))

def make_opp(agent_name: str, symbol_str: str, side: OrderSide, age_min: int = 0) -> Opportunity:
    now = datetime.now(timezone.utc) - timedelta(minutes=age_min)
    return Opportunity(
        id=f"opp_{agent_name}",
        agent_name=agent_name,
        symbol=Symbol(symbol_str),
        signal="TEST",
        confidence=1.0,
        reasoning="Test",
        data={},
        timestamp=now,
        status=OpportunityStatus.PENDING,
        suggested_trade=MarketOrder(
            symbol=Symbol(symbol_str),
            side=side,
            quantity=Decimal("10"),
            account_id="test"
        )
    )

@pytest.mark.asyncio
async def test_consensus_router():
    target = StubRouter()
    # Require 2 agents within 15 minutes
    router = ConsensusRouter(target_router=target, threshold=2, window_minutes=15) # type: ignore
    
    # Agent 1 suggests BUY AAPL
    opp1 = make_opp("agent_1", "AAPL", OrderSide.BUY, age_min=5)
    await router.route(opp1, ActionLevel.SUGGEST_TRADE)
    
    assert len(target.routes) == 1
    assert target.routes[0][1] == ActionLevel.SUGGEST_TRADE
    
    # Agent 2 suggests SELL AAPL (different side)
    opp2 = make_opp("agent_2", "AAPL", OrderSide.SELL, age_min=2)
    await router.route(opp2, ActionLevel.SUGGEST_TRADE)
    
    assert len(target.routes) == 2
    assert target.routes[1][1] == ActionLevel.SUGGEST_TRADE
    
    # Agent 3 suggests BUY AAPL within window (matches opp1)
    opp3 = make_opp("agent_3", "AAPL", OrderSide.BUY, age_min=1)
    await router.route(opp3, ActionLevel.SUGGEST_TRADE)
    
    assert len(target.routes) == 3
    # Consensus reached, so action level should be AUTO_EXECUTE
    assert target.routes[2][1] == ActionLevel.AUTO_EXECUTE
    assert "Consensus reached" in target.routes[2][0].reasoning

@pytest.mark.asyncio
async def test_consensus_window_expiry():
    target = StubRouter()
    # Require 2 agents within 15 minutes
    router = ConsensusRouter(target_router=target, threshold=2, window_minutes=15) # type: ignore
    
    # Agent 1 suggests BUY AAPL 20 minutes ago
    opp1 = make_opp("agent_1", "AAPL", OrderSide.BUY, age_min=20)
    await router.route(opp1, ActionLevel.SUGGEST_TRADE)
    
    # Agent 2 suggests BUY AAPL now
    opp2 = make_opp("agent_2", "AAPL", OrderSide.BUY, age_min=0)
    await router.route(opp2, ActionLevel.SUGGEST_TRADE)
    
    # Should not trigger consensus because opp1 is outside the 15 min window
    assert len(target.routes) == 2
    assert target.routes[1][1] == ActionLevel.SUGGEST_TRADE
