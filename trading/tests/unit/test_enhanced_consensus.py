"""Tests for enhanced consensus system: AgentWeightProvider, EnhancedConsensusRouter, ConsensusConfig."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agents.models import ActionLevel, Opportunity, OpportunityStatus
from broker.models import OrderSide, Symbol, MarketOrder
from agents.consensus import (
    ConsensusConfig,
    EnhancedConsensusRouter,
    AgentWeightProvider,
    AgentWeightProfile,
    WeightSource,
)


class StubRouter:
    """Captures routed opportunities for assertion."""

    def __init__(self):
        self.routes = []

    async def route(self, opportunity, action_level):
        self.routes.append((opportunity, action_level))


def make_opp(
    agent_name: str,
    symbol_str: str,
    side: OrderSide,
    confidence: float = 1.0,
    age_min: int = 0,
    data: dict | None = None,
) -> Opportunity:
    now = datetime.now(timezone.utc) - timedelta(minutes=age_min)
    return Opportunity(
        id=f"opp_{agent_name}_{symbol_str}",
        agent_name=agent_name,
        symbol=Symbol(symbol_str),
        signal="TEST",
        confidence=confidence,
        reasoning=f"Test reasoning for {agent_name}",
        data=data or {},
        timestamp=now,
        status=OpportunityStatus.PENDING,
        suggested_trade=MarketOrder(
            symbol=Symbol(symbol_str),
            side=side,
            quantity=Decimal("10"),
            account_id="test",
        ),
    )


# --- AgentWeightProvider tests ---


class TestAgentWeightProvider:
    def test_equal_weight(self):
        provider = AgentWeightProvider()
        config = ConsensusConfig(weight_source=WeightSource.EQUAL)
        opp = make_opp("agent_1", "AAPL", OrderSide.BUY, confidence=0.5)
        weight = provider.compute_vote_weight(opp, config)
        assert weight == 1.0

    def test_confidence_weight(self):
        provider = AgentWeightProvider()
        config = ConsensusConfig(weight_source=WeightSource.CONFIDENCE)
        opp = make_opp("agent_1", "AAPL", OrderSide.BUY, confidence=0.7)
        weight = provider.compute_vote_weight(opp, config)
        assert weight == pytest.approx(0.7)

    def test_confidence_weight_floored_at_0_01(self):
        provider = AgentWeightProvider()
        config = ConsensusConfig(weight_source=WeightSource.CONFIDENCE)
        opp = make_opp("agent_1", "AAPL", OrderSide.BUY, confidence=0.0)
        weight = provider.compute_vote_weight(opp, config)
        assert weight == 0.01

    def test_sharpe_weight(self):
        provider = AgentWeightProvider()
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_1",
                sharpe_ratio=2.0,
                elo_rating=1500,
                total_trades=200,
                win_rate=55.0,
            )
        )
        config = ConsensusConfig(weight_source=WeightSource.SHARPE)
        opp = make_opp("agent_1", "AAPL", OrderSide.BUY)
        weight = provider.compute_vote_weight(opp, config)
        # Sharpe 2.0 → (2 + 2) / 6 = 0.6667
        assert weight == pytest.approx(0.6667, abs=0.001)

    def test_elo_weight(self):
        provider = AgentWeightProvider()
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_1",
                sharpe_ratio=1.0,
                elo_rating=1500,
                total_trades=100,
                win_rate=50.0,
            )
        )
        config = ConsensusConfig(weight_source=WeightSource.ELO)
        opp = make_opp("agent_1", "AAPL", OrderSide.BUY)
        weight = provider.compute_vote_weight(opp, config)
        # ELO 1500 → (1500 - 800) / 1400 = 0.5
        assert weight == pytest.approx(0.5, abs=0.001)

    def test_composite_weight(self):
        provider = AgentWeightProvider()
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_1",
                sharpe_ratio=2.0,
                elo_rating=1800,
                total_trades=300,
                win_rate=60.0,
            )
        )
        config = ConsensusConfig(
            weight_source=WeightSource.COMPOSITE,
            confidence_weight=0.5,
            sharpe_weight=0.3,
            elo_weight=0.2,
        )
        opp = make_opp("agent_1", "AAPL", OrderSide.BUY, confidence=0.8)
        weight = provider.compute_vote_weight(opp, config)
        # confidence=0.8, sharpe_norm=(2+2)/6=0.667, elo_norm=(1800-800)/1400=0.714
        # blended = 0.5*0.8 + 0.3*0.667 + 0.2*0.714 ≈ 0.725
        assert weight == pytest.approx(0.725, abs=0.01)

    def test_unknown_agent_fallback(self):
        provider = AgentWeightProvider()
        config = ConsensusConfig(weight_source=WeightSource.SHARPE)
        opp = make_opp("unknown_agent", "AAPL", OrderSide.BUY, confidence=0.6)
        weight = provider.compute_vote_weight(opp, config)
        # Unknown agent falls back to confidence
        assert weight == pytest.approx(0.6)

    def test_load_from_leaderboard(self):
        provider = AgentWeightProvider()
        rankings = [
            {
                "agent_name": "agent_1",
                "sharpe_ratio": 1.5,
                "elo": 1400,
                "total_trades": 200,
                "win_rate": 52.0,
            },
            {
                "agent_name": "agent_2",
                "sharpe_ratio": 2.2,
                "elo": 1600,
                "total_trades": 400,
                "win_rate": 61.0,
            },
        ]
        provider.load_from_leaderboard(rankings)
        p1 = provider.get_profile("agent_1")
        p2 = provider.get_profile("agent_2")
        assert p1 is not None
        assert p1.sharpe_ratio == 1.5
        assert p2.elo_rating == 1600

    def test_composite_score(self):
        profile = AgentWeightProfile(
            agent_name="test",
            sharpe_ratio=2.0,
            elo_rating=1800,
            total_trades=300,
            win_rate=60.0,
        )
        score = profile.composite_score()
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # strong profile should score > 0.5


# --- EnhancedConsensusRouter tests ---


class TestEnhancedConsensusRouter:
    @pytest.mark.asyncio
    async def test_basic_threshold(self):
        """2-of-3 threshold: first vote passes through, second triggers auto_execute."""
        target = StubRouter()
        config = ConsensusConfig(threshold=2, weight_source=WeightSource.EQUAL)
        router = EnhancedConsensusRouter(target_router=target, config=config)

        opp1 = make_opp("agent_1", "AAPL", OrderSide.BUY)
        await router.route(opp1, ActionLevel.SUGGEST_TRADE)
        assert len(target.routes) == 1
        assert target.routes[0][1] == ActionLevel.SUGGEST_TRADE

        opp2 = make_opp("agent_2", "AAPL", OrderSide.BUY)
        await router.route(opp2, ActionLevel.SUGGEST_TRADE)
        assert len(target.routes) == 2
        assert target.routes[1][1] == ActionLevel.AUTO_EXECUTE

    @pytest.mark.asyncio
    async def test_weight_threshold(self):
        """Weight-based consensus: requires weight_ratio >= threshold."""
        target = StubRouter()
        provider = AgentWeightProvider()
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_1",
                sharpe_ratio=3.0,
                elo_rating=2000,
                total_trades=500,
                win_rate=65.0,
            )
        )
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_2",
                sharpe_ratio=0.5,
                elo_rating=1100,
                total_trades=50,
                win_rate=45.0,
            )
        )
        config = ConsensusConfig(
            threshold=2,
            weight_source=WeightSource.SHARPE,
            weight_threshold=0.6,
        )
        router = EnhancedConsensusRouter(
            target_router=target, config=config, weight_provider=provider
        )

        # Agent 1 (high Sharpe ~0.833) + Agent 2 (low Sharpe ~0.417) = avg ~0.625 > 0.6
        opp1 = make_opp("agent_1", "AAPL", OrderSide.BUY)
        await router.route(opp1, ActionLevel.SUGGEST_TRADE)

        opp2 = make_opp("agent_2", "AAPL", OrderSide.BUY)
        await router.route(opp2, ActionLevel.SUGGEST_TRADE)

        assert len(target.routes) == 2
        assert target.routes[1][1] == ActionLevel.AUTO_EXECUTE

    @pytest.mark.asyncio
    async def test_regime_threshold(self):
        """Regime-specific threshold overrides default."""
        target = StubRouter()
        config = ConsensusConfig(
            threshold=2,
            regime_thresholds={"high_volatility": 3},
        )
        router = EnhancedConsensusRouter(target_router=target, config=config)

        # Normal regime: 2 agents should trigger consensus
        opp1 = make_opp(
            "agent_1",
            "AAPL",
            OrderSide.BUY,
            data={"regime": {"trend": "up", "volatility": "low"}},
        )
        opp2 = make_opp(
            "agent_2",
            "AAPL",
            OrderSide.BUY,
            data={"regime": {"trend": "up", "volatility": "low"}},
        )
        await router.route(opp1, ActionLevel.SUGGEST_TRADE)
        await router.route(opp2, ActionLevel.SUGGEST_TRADE)
        assert target.routes[-1][1] == ActionLevel.AUTO_EXECUTE  # 2 >= 2

        # High volatility regime: need 3 agents
        target.routes.clear()
        router._pending.clear()
        opp3 = make_opp(
            "agent_1",
            "TSLA",
            OrderSide.BUY,
            data={"regime": {"trend": "down", "volatility": "high"}},
        )
        opp4 = make_opp(
            "agent_2",
            "TSLA",
            OrderSide.BUY,
            data={"regime": {"trend": "down", "volatility": "high"}},
        )
        await router.route(opp3, ActionLevel.SUGGEST_TRADE)
        await router.route(opp4, ActionLevel.SUGGEST_TRADE)
        assert target.routes[-1][1] == ActionLevel.SUGGEST_TRADE  # 2 < 3, no consensus

    @pytest.mark.asyncio
    async def test_unanimous_regime(self):
        """Unanimous regime requires all available agents."""
        target = StubRouter()
        config = ConsensusConfig(
            threshold=2,
            unanimous_regimes=["crisis"],
        )
        router = EnhancedConsensusRouter(target_router=target, config=config)

        opp1 = make_opp("agent_1", "AAPL", OrderSide.BUY, data={"regime": "crisis"})
        await router.route(opp1, ActionLevel.SUGGEST_TRADE)
        assert (
            target.routes[-1][1] == ActionLevel.SUGGEST_TRADE
        )  # only 1 agent, not unanimous

        opp2 = make_opp("agent_2", "AAPL", OrderSide.BUY, data={"regime": "crisis"})
        await router.route(opp2, ActionLevel.SUGGEST_TRADE)
        assert target.routes[-1][1] == ActionLevel.AUTO_EXECUTE  # 2 agents, unanimous

    @pytest.mark.asyncio
    async def test_disabled_passthrough(self):
        """When disabled, opportunities pass through directly."""
        target = StubRouter()
        config = ConsensusConfig(enabled=False, threshold=10)
        router = EnhancedConsensusRouter(target_router=target, config=config)

        opp = make_opp("agent_1", "AAPL", OrderSide.BUY)
        await router.route(opp, ActionLevel.SUGGEST_TRADE)
        assert len(target.routes) == 1
        assert target.routes[0][1] == ActionLevel.SUGGEST_TRADE

    @pytest.mark.asyncio
    async def test_window_expiry(self):
        """Votes outside the window are expired."""
        target = StubRouter()
        config = ConsensusConfig(threshold=2, window_minutes=5)
        router = EnhancedConsensusRouter(target_router=target, config=config)

        opp_old = make_opp("agent_1", "AAPL", OrderSide.BUY, age_min=10)
        await router.route(opp_old, ActionLevel.SUGGEST_TRADE)
        assert target.routes[-1][1] == ActionLevel.SUGGEST_TRADE

        opp_new = make_opp("agent_2", "AAPL", OrderSide.BUY, age_min=1)
        await router.route(opp_new, ActionLevel.SUGGEST_TRADE)
        # opp_old expired, only 1 valid vote
        assert target.routes[-1][1] == ActionLevel.SUGGEST_TRADE

    @pytest.mark.asyncio
    async def test_collect_vote_backtesting(self):
        """collect_vote() works for backtesting integration."""
        provider = AgentWeightProvider()
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_1",
                sharpe_ratio=2.0,
                elo_rating=1500,
                total_trades=100,
                win_rate=55.0,
            )
        )
        config = ConsensusConfig(weight_source=WeightSource.SHARPE)
        router = EnhancedConsensusRouter(
            target_router=StubRouter(), config=config, weight_provider=provider
        )

        opp = make_opp("agent_1", "AAPL", OrderSide.BUY)
        vote = router.collect_vote(opp, regime="bull")
        assert vote.agent_name == "agent_1"
        assert vote.symbol == "AAPL"
        assert vote.side == "BUY"
        assert vote.weight == pytest.approx(0.6667, abs=0.001)
        assert vote.regime == "bull"

    @pytest.mark.asyncio
    async def test_check_votes_consensus(self):
        """check_votes_consensus() returns (bool, weight, reason)."""
        provider = AgentWeightProvider()
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_1",
                sharpe_ratio=2.0,
                elo_rating=1500,
                total_trades=100,
                win_rate=55.0,
            )
        )
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_2",
                sharpe_ratio=1.5,
                elo_rating=1300,
                total_trades=80,
                win_rate=50.0,
            )
        )
        config = ConsensusConfig(threshold=2, weight_source=WeightSource.SHARPE)
        router = EnhancedConsensusRouter(
            target_router=StubRouter(), config=config, weight_provider=provider
        )

        opp1 = make_opp("agent_1", "AAPL", OrderSide.BUY)
        opp2 = make_opp("agent_2", "AAPL", OrderSide.BUY)
        votes = [router.collect_vote(opp1), router.collect_vote(opp2)]
        reached, weight, reason = router.check_votes_consensus(votes)
        assert reached is True
        assert weight > 0
        assert "count_threshold_met" in reason

    @pytest.mark.asyncio
    async def test_min_agents(self):
        """min_agents prevents consensus with too few agents."""
        target = StubRouter()
        config = ConsensusConfig(threshold=1, min_agents=2)
        router = EnhancedConsensusRouter(target_router=target, config=config)

        opp = make_opp("agent_1", "AAPL", OrderSide.BUY)
        await router.route(opp, ActionLevel.SUGGEST_TRADE)
        assert target.routes[-1][1] == ActionLevel.SUGGEST_TRADE  # only 1 agent, need 2

    @pytest.mark.asyncio
    async def test_consensus_annotates_reasoning(self):
        """Consensus reason is appended to opportunity reasoning."""
        target = StubRouter()
        config = ConsensusConfig(threshold=2, weight_source=WeightSource.EQUAL)
        router = EnhancedConsensusRouter(target_router=target, config=config)

        opp1 = make_opp("agent_1", "AAPL", OrderSide.BUY)
        await router.route(opp1, ActionLevel.SUGGEST_TRADE)

        opp2 = make_opp("agent_2", "AAPL", OrderSide.BUY)
        await router.route(opp2, ActionLevel.SUGGEST_TRADE)

        # The second opportunity (which triggers consensus) should have annotated reasoning
        consensus_opp = target.routes[-1][0]
        assert "Consensus:" in consensus_opp.reasoning
        assert "agents=agent_1,agent_2" in consensus_opp.reasoning
