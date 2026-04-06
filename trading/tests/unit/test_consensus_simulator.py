"""Tests for ConsensusSimulator — end-to-end consensus backtesting."""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal

from broker.models import Bar, Symbol, OrderSide, MarketOrder
from agents.models import Opportunity, OpportunityStatus
from agents.consensus import (
    ConsensusConfig,
    AgentWeightProvider,
    AgentWeightProfile,
    WeightSource,
)
from backtesting.models import BacktestConfig, CommissionModel
from backtesting.consensus_sim import ConsensusSimulator


def _make_bar(ticker: str, day: int, close: float = 150.0) -> Bar:
    """Create a test bar."""
    return Bar(
        symbol=Symbol(ticker),
        timestamp=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        open=Decimal(str(close)),
        high=Decimal(str(close + 1)),
        low=Decimal(str(close - 1)),
        close=Decimal(str(close)),
        volume=1000000,
    )


def _make_bars(ticker: str, count: int = 200, start_price: float = 150.0) -> list[Bar]:
    """Create a series of bars for backtesting."""
    bars = []
    for i in range(count):
        price = start_price + i * 0.1  # slight uptrend
        bars.append(
            Bar(
                symbol=Symbol(ticker),
                timestamp=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                open=Decimal(str(price)),
                high=Decimal(str(price + 1)),
                low=Decimal(str(price - 1)),
                close=Decimal(str(price)),
                volume=1000000,
            )
        )
    return bars


class MockAgent:
    """Mock agent that returns fixed opportunities."""

    def __init__(self, name: str, opportunities: list[Opportunity]):
        self.name = name
        self._opps = opportunities
        self._call_count = 0

    async def scan(self, data_bus):
        # Return the same opportunities each call for simplicity
        return self._opps


def _make_config(name: str = "test_backtest") -> BacktestConfig:
    return BacktestConfig(
        name=name,
        agent_names=["agent_1", "agent_2"],
        symbols=["AAPL"],
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        timeframe="1d",
        initial_capital=Decimal("100000"),
        commission=CommissionModel.ZERO,
        warmup_bars=0,
    )


class TestConsensusSimulator:
    @pytest.mark.asyncio
    async def test_simulator_runs_without_error(self):
        """Basic smoke test: simulator runs and returns a result."""
        config = _make_config()
        bars_dict = {"AAPL": _make_bars("AAPL", count=20)}

        opp = Opportunity(
            id="opp_1",
            agent_name="agent_1",
            symbol=Symbol("AAPL"),
            signal="BUY",
            confidence=0.8,
            reasoning="Test buy",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        agent = MockAgent("agent_1", [opp])

        consensus_config = ConsensusConfig(
            threshold=1, weight_source=WeightSource.EQUAL
        )
        simulator = ConsensusSimulator(consensus_config=consensus_config)

        result = await simulator.run(config, [agent], bars_dict)

        assert result.backtest_result.status.value == "completed"
        assert result.consensus_metrics.total_agents == 1

    @pytest.mark.asyncio
    async def test_consensus_filters_trades(self):
        """With threshold=2 and only 1 agent, all trades should be filtered."""
        config = _make_config()
        bars_dict = {"AAPL": _make_bars("AAPL", count=20)}

        opp = Opportunity(
            id="opp_1",
            agent_name="agent_1",
            symbol=Symbol("AAPL"),
            signal="BUY",
            confidence=0.8,
            reasoning="Test buy",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        agent = MockAgent("agent_1", [opp])

        consensus_config = ConsensusConfig(
            threshold=2, weight_source=WeightSource.EQUAL
        )
        simulator = ConsensusSimulator(consensus_config=consensus_config)

        result = await simulator.run(config, [agent], bars_dict)

        assert result.backtest_result.status.value == "completed"
        assert result.consensus_metrics.consensus_trades == 0
        assert result.consensus_metrics.filtered_trades > 0
        assert result.consensus_metrics.consensus_rate == 0.0

    @pytest.mark.asyncio
    async def test_consensus_passes_with_two_agents(self):
        """With threshold=2 and 2 agents, trades should reach consensus."""
        config = _make_config()
        bars_dict = {"AAPL": _make_bars("AAPL", count=20)}

        opp1 = Opportunity(
            id="opp_1",
            agent_name="agent_1",
            symbol=Symbol("AAPL"),
            signal="BUY",
            confidence=0.8,
            reasoning="Test buy",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        opp2 = Opportunity(
            id="opp_2",
            agent_name="agent_2",
            symbol=Symbol("AAPL"),
            signal="BUY",
            confidence=0.7,
            reasoning="Test buy",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        agent1 = MockAgent("agent_1", [opp1])
        agent2 = MockAgent("agent_2", [opp2])

        consensus_config = ConsensusConfig(
            threshold=2, weight_source=WeightSource.EQUAL
        )
        simulator = ConsensusSimulator(consensus_config=consensus_config)

        result = await simulator.run(config, [agent1, agent2], bars_dict)

        assert result.backtest_result.status.value == "completed"
        assert result.consensus_metrics.consensus_trades > 0
        assert result.consensus_metrics.filtered_trades == 0
        assert result.consensus_metrics.consensus_rate > 0.0

    @pytest.mark.asyncio
    async def test_consensus_metrics_tracked(self):
        """Consensus metrics are populated correctly."""
        config = _make_config()
        bars_dict = {"AAPL": _make_bars("AAPL", count=20)}

        opp1 = Opportunity(
            id="opp_1",
            agent_name="agent_1",
            symbol=Symbol("AAPL"),
            signal="BUY",
            confidence=0.9,
            reasoning="High confidence buy",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        opp2 = Opportunity(
            id="opp_2",
            agent_name="agent_2",
            symbol=Symbol("AAPL"),
            signal="BUY",
            confidence=0.6,
            reasoning="Low confidence buy",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        agent1 = MockAgent("agent_1", [opp1])
        agent2 = MockAgent("agent_2", [opp2])

        provider = AgentWeightProvider()
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_1",
                sharpe_ratio=2.0,
                elo_rating=1600,
                total_trades=200,
                win_rate=60.0,
            )
        )
        provider.update_profile(
            AgentWeightProfile(
                agent_name="agent_2",
                sharpe_ratio=1.0,
                elo_rating=1200,
                total_trades=100,
                win_rate=50.0,
            )
        )
        consensus_config = ConsensusConfig(
            threshold=2,
            weight_source=WeightSource.SHARPE,
        )
        simulator = ConsensusSimulator(
            consensus_config=consensus_config,
            weight_provider=provider,
        )

        result = await simulator.run(config, [agent1, agent2], bars_dict)

        metrics = result.consensus_metrics
        assert metrics.total_opportunities > 0
        assert metrics.consensus_trades > 0
        assert metrics.avg_consensus_weight > 0
        assert metrics.avg_votes_per_consensus == pytest.approx(2.0, abs=0.1)
        assert metrics.weight_source == "sharpe"
        assert metrics.config_snapshot["threshold"] == 2

    @pytest.mark.asyncio
    async def test_different_sides_not_consensus(self):
        """BUY and SELL votes should not reach consensus (different side)."""
        config = _make_config()
        bars_dict = {"AAPL": _make_bars("AAPL", count=20)}

        opp_buy = Opportunity(
            id="opp_1",
            agent_name="agent_1",
            symbol=Symbol("AAPL"),
            signal="BUY",
            confidence=0.8,
            reasoning="Buy",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        opp_sell = Opportunity(
            id="opp_2",
            agent_name="agent_2",
            symbol=Symbol("AAPL"),
            signal="SELL",
            confidence=0.8,
            reasoning="Sell",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.SELL,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        agent1 = MockAgent("agent_1", [opp_buy])
        agent2 = MockAgent("agent_2", [opp_sell])

        consensus_config = ConsensusConfig(
            threshold=2, weight_source=WeightSource.EQUAL
        )
        simulator = ConsensusSimulator(consensus_config=consensus_config)

        result = await simulator.run(config, [agent1, agent2], bars_dict)

        # BUY and SELL are different sides, so each has only 1 vote — no consensus
        assert result.consensus_metrics.consensus_trades == 0
        assert result.consensus_metrics.filtered_trades > 0

    @pytest.mark.asyncio
    async def test_simulator_produces_equity_curve(self):
        """The simulator should produce an equity curve even with consensus filtering."""
        config = _make_config()
        bars_dict = {"AAPL": _make_bars("AAPL", count=50)}

        opp = Opportunity(
            id="opp_1",
            agent_name="agent_1",
            symbol=Symbol("AAPL"),
            signal="BUY",
            confidence=0.8,
            reasoning="Buy",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        agent = MockAgent("agent_1", [opp])

        consensus_config = ConsensusConfig(
            threshold=1, weight_source=WeightSource.EQUAL
        )
        simulator = ConsensusSimulator(consensus_config=consensus_config)

        result = await simulator.run(config, [agent], bars_dict)

        assert len(result.backtest_result.equity_curve) > 0
        assert result.backtest_result.final_equity > Decimal("0")

    @pytest.mark.asyncio
    async def test_to_dict(self):
        """ConsensusSimulationResult.to_dict() includes consensus_metrics."""
        config = _make_config()
        bars_dict = {"AAPL": _make_bars("AAPL", count=10)}

        opp = Opportunity(
            id="opp_1",
            agent_name="agent_1",
            symbol=Symbol("AAPL"),
            signal="BUY",
            confidence=0.8,
            reasoning="Buy",
            data={},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=Symbol("AAPL"),
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="test",
            ),
        )
        agent = MockAgent("agent_1", [opp])

        consensus_config = ConsensusConfig(
            threshold=1, weight_source=WeightSource.EQUAL
        )
        simulator = ConsensusSimulator(consensus_config=consensus_config)

        result = await simulator.run(config, [agent], bars_dict)
        d = result.to_dict()

        assert "consensus_metrics" in d
        assert "total_opportunities" in d["consensus_metrics"]
        assert "consensus_trades" in d["consensus_metrics"]
        assert "sharpe_ratio" in d  # standard backtest metrics still present
