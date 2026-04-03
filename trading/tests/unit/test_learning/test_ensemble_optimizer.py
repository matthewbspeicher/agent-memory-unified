"""Tests for EnsembleOptimizer."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from agents.models import AgentSignal
from learning.ensemble_optimizer import (
    AgentWeight,
    EnsembleConfig,
    EnsembleMethod,
    EnsembleOptimizer,
    EnsembleSignal,
)


class TestEnsembleConfig:
    """Tests for EnsembleConfig."""

    def test_default_config(self):
        cfg = EnsembleConfig()
        assert cfg.enabled is True
        assert cfg.method == EnsembleMethod.SHARPE_WEIGHTED
        assert cfg.min_agents_for_ensemble == 2
        assert cfg.max_weight_single_agent == 0.5

    def test_from_dict(self):
        data = {
            "enabled": False,
            "method": "majority_vote",
            "min_agents_for_ensemble": 3,
        }
        cfg = EnsembleConfig.from_agent_config(data)
        assert cfg.enabled is False
        assert cfg.method == EnsembleMethod.MAJORITY_VOTE
        assert cfg.min_agents_for_ensemble == 3


class TestEnsembleOptimizer:
    """Tests for EnsembleOptimizer class."""

    @pytest.fixture
    def mock_runner(self):
        runner = MagicMock()
        agent_a = MagicMock()
        agent_a.name = "agent_a"
        agent_b = MagicMock()
        agent_b.name = "agent_b"
        agent_c = MagicMock()
        agent_c.name = "agent_c"
        runner.list_agents = MagicMock(return_value=[agent_a, agent_b, agent_c])
        return runner

    @pytest.fixture
    def mock_perf_store(self):
        store = AsyncMock()
        # Mock performance snapshots - using balanced Sharpe ratios so cap works correctly
        snapshot_a = MagicMock()
        snapshot_a.sharpe_ratio = 1.0
        snapshot_a.total_trades = 100

        snapshot_b = MagicMock()
        snapshot_b.sharpe_ratio = 0.8
        snapshot_b.total_trades = 50

        snapshot_c = MagicMock()
        snapshot_c.sharpe_ratio = 0.6
        snapshot_c.total_trades = 20

        async def get_latest(name):
            if name == "agent_a":
                return snapshot_a
            elif name == "agent_b":
                return snapshot_b
            elif name == "agent_c":
                return snapshot_c
            return None

        store.get_latest = AsyncMock(side_effect=get_latest)
        return store

    @pytest.fixture
    def optimizer(self, mock_runner, mock_perf_store):
        return EnsembleOptimizer(
            runner=mock_runner,
            perf_store=mock_perf_store,
            config=EnsembleConfig(),
        )

    @pytest.mark.asyncio
    async def test_compute_agent_weights_basic(self, optimizer):
        weights = await optimizer.compute_agent_weights()
        assert len(weights) == 3
        # agent_a should have highest weight (highest Sharpe)
        assert weights[0].agent_name == "agent_a"
        assert weights[0].sharpe_ratio == 1.0
        # Weights should sum to ~1.0
        total = sum(w.adjusted_weight for w in weights)
        assert abs(total - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_compute_agent_weights_respects_cap(self, optimizer):
        weights = await optimizer.compute_agent_weights()
        for w in weights:
            assert w.base_weight <= 0.5
            assert w.adjusted_weight <= 0.5

    @pytest.mark.asyncio
    async def test_compute_agent_weights_sorted(self, optimizer):
        weights = await optimizer.compute_agent_weights()
        # Should be sorted by adjusted_weight descending
        for i in range(len(weights) - 1):
            assert weights[i].adjusted_weight >= weights[i + 1].adjusted_weight

    @pytest.mark.asyncio
    async def test_combine_signals_empty(self, optimizer):
        result = await optimizer.combine_signals("AAPL", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_combine_signals_below_threshold(self, optimizer):
        signals = [
            AgentSignal(
                signal_type="trade",
                source_agent="agent_a",
                payload={"direction": "bullish", "confidence": 0.6},
                timestamp=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc),
            ),
        ]
        result = await optimizer.combine_signals("AAPL", signals)
        # Only 1 signal, below min_agents_for_ensemble (2)
        assert result is None

    @pytest.mark.asyncio
    async def test_combine_signals_bullish_consensus(self, optimizer):
        now = datetime.now(timezone.utc)
        signals = [
            AgentSignal(
                signal_type="trade",
                source_agent="agent_a",
                payload={"direction": "bullish", "confidence": 0.8},
                timestamp=now,
                expires_at=now,
            ),
            AgentSignal(
                signal_type="trade",
                source_agent="agent_b",
                payload={"direction": "bullish", "confidence": 0.7},
                timestamp=now,
                expires_at=now,
            ),
        ]
        result = await optimizer.combine_signals("AAPL", signals)
        assert result is not None
        assert result.direction == "bullish"
        assert result.symbol == "AAPL"
        assert result.agent_count == 2

    @pytest.mark.asyncio
    async def test_combine_signals_bearish_consensus(self, optimizer):
        now = datetime.now(timezone.utc)
        signals = [
            AgentSignal(
                signal_type="trade",
                source_agent="agent_a",
                payload={"direction": "bearish", "confidence": 0.9},
                timestamp=now,
                expires_at=now,
            ),
            AgentSignal(
                signal_type="trade",
                source_agent="agent_b",
                payload={"direction": "bearish", "confidence": 0.8},
                timestamp=now,
                expires_at=now,
            ),
        ]
        result = await optimizer.combine_signals("AAPL", signals)
        assert result is not None
        assert result.direction == "bearish"

    @pytest.mark.asyncio
    async def test_combine_signals_mixed_direction(self, optimizer):
        now = datetime.now(timezone.utc)
        signals = [
            AgentSignal(
                signal_type="trade",
                source_agent="agent_a",  # High weight agent (Sharpe 1.0)
                payload={"direction": "bullish", "confidence": 0.8},
                timestamp=now,
                expires_at=now,
            ),
            AgentSignal(
                signal_type="trade",
                source_agent="agent_c",  # Low weight agent (Sharpe 0.6)
                payload={"direction": "bearish", "confidence": 0.9},
                timestamp=now,
                expires_at=now,
            ),
        ]
        result = await optimizer.combine_signals("AAPL", signals)
        assert result is not None
        # High-weight bullish agent should dominate
        assert result.direction == "bullish"

    @pytest.mark.asyncio
    async def test_combine_signals_invalid_direction_ignored(self, optimizer):
        now = datetime.now(timezone.utc)
        signals = [
            AgentSignal(
                signal_type="trade",
                source_agent="agent_a",
                payload={"direction": "invalid", "confidence": 0.8},
                timestamp=now,
                expires_at=now,
            ),
            AgentSignal(
                signal_type="trade",
                source_agent="agent_b",
                payload={"direction": "bullish", "confidence": 0.7},
                timestamp=now,
                expires_at=now,
            ),
        ]
        result = await optimizer.combine_signals("AAPL", signals)
        # Only 1 valid signal, below threshold
        assert result is None

    @pytest.mark.asyncio
    async def test_get_weight_report(self, optimizer):
        report = await optimizer.get_weight_report()
        assert len(report) == 3
        assert all("agent" in r for r in report)
        assert all("sharpe_ratio" in r for r in report)

    def test_get_method_description(self, optimizer):
        desc = optimizer.get_method_description()
        assert "Sharpe" in desc


class TestAgentWeight:
    """Tests for AgentWeight dataclass."""

    def test_agent_weight_creation(self):
        weight = AgentWeight(
            agent_name="test_agent",
            base_weight=0.3,
            adjusted_weight=0.3,
            sharpe_ratio=1.2,
            trade_count=50,
            is_correlated=False,
        )
        assert weight.agent_name == "test_agent"
        assert weight.sharpe_ratio == 1.2
        assert weight.is_correlated is False

    def test_agent_weight_correlated(self):
        weight = AgentWeight(
            agent_name="test_agent",
            base_weight=0.3,
            adjusted_weight=0.15,  # Penalty applied
            sharpe_ratio=1.2,
            trade_count=50,
            is_correlated=True,
        )
        assert weight.is_correlated is True
        assert weight.adjusted_weight < weight.base_weight
