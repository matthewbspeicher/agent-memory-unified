"""Tests for CorrelationMonitor and CorrelationStore."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from learning.correlation_monitor import (
    CorrelationAlertLevel,
    CorrelationConfig,
    CorrelationMonitor,
    CorrelationPair,
    CorrelationSnapshot,
    compute_diversification_score,
    compute_pearson_correlation,
)
from storage.correlation import CorrelationStore


class TestComputePearsonCorrelation:
    """Tests for the pure Pearson correlation function."""

    def test_perfect_positive_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        result = compute_pearson_correlation(x, y)
        assert result is not None
        assert abs(result - 1.0) < 1e-6

    def test_perfect_negative_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        result = compute_pearson_correlation(x, y)
        assert result is not None
        assert abs(result - (-1.0)) < 1e-6

    def test_no_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [5.0, 3.0, 5.0, 3.0, 5.0]
        result = compute_pearson_correlation(x, y)
        assert result is not None
        assert abs(result) < 0.5  # Low correlation

    def test_different_lengths_returns_none(self):
        x = [1.0, 2.0, 3.0]
        y = [1.0, 2.0]
        assert compute_pearson_correlation(x, y) is None

    def test_too_few_points_returns_none(self):
        x = [1.0, 2.0]
        y = [3.0, 4.0]
        assert compute_pearson_correlation(x, y) is None

    def test_zero_variance_returns_none(self):
        x = [1.0, 1.0, 1.0, 1.0]
        y = [1.0, 2.0, 3.0, 4.0]
        assert compute_pearson_correlation(x, y) is None


class TestComputeDiversificationScore:
    """Tests for portfolio diversification score."""

    def test_empty_list_returns_one(self):
        assert compute_diversification_score([]) == 1.0

    def test_all_correlated_returns_low(self):
        # All high positive correlations
        corrs = [0.8, 0.9, 0.85, 0.95]
        score = compute_diversification_score(corrs)
        assert score < 0.2

    def test_mixed_correlations_returns_medium(self):
        corrs = [0.5, -0.3, 0.2, -0.4]
        score = compute_diversification_score(corrs)
        assert 0.3 < score < 0.7

    def test_all_uncorrelated_returns_high(self):
        corrs = [0.0, 0.0, 0.0]
        score = compute_diversification_score(corrs)
        assert score > 0.9


class TestCorrelationConfig:
    """Tests for CorrelationConfig."""

    def test_default_config(self):
        cfg = CorrelationConfig()
        assert cfg.enabled is True
        assert cfg.lookback_days == 30
        assert cfg.high_correlation_threshold == 0.7

    def test_from_dict(self):
        data = {
            "enabled": False,
            "lookback_days": 60,
            "high_correlation_threshold": 0.8,
        }
        cfg = CorrelationConfig.from_learning_config(data)
        assert cfg.enabled is False
        assert cfg.lookback_days == 60
        assert cfg.high_correlation_threshold == 0.8

    def test_from_none(self):
        cfg = CorrelationConfig.from_learning_config(None)
        assert cfg.enabled is True


class TestCorrelationSnapshot:
    """Tests for CorrelationSnapshot dataclass."""

    def test_snapshot_creation(self):
        snapshot = CorrelationSnapshot(
            timestamp=datetime.now(timezone.utc),
            alert_level=CorrelationAlertLevel.WARNING,
            portfolio_diversification_score=0.4,
            high_correlation_pairs=[],
            agent_count=5,
            analyzed_pairs=10,
            skipped_pairs=2,
        )
        assert snapshot.alert_level == CorrelationAlertLevel.WARNING
        assert snapshot.agent_count == 5


class TestCorrelationMonitor:
    """Tests for CorrelationMonitor class."""

    @pytest.fixture
    def mock_perf_store(self):
        store = AsyncMock()
        store.get_all_latest = AsyncMock(
            return_value=[
                MagicMock(agent_name="agent_a"),
                MagicMock(agent_name="agent_b"),
            ]
        )
        store.get_daily_pnl_series = AsyncMock(
            return_value=[100.0, 105.0, 102.0, 108.0, 110.0]
        )
        return store

    @pytest.fixture
    def mock_correlation_store(self):
        store = AsyncMock()
        store.save_snapshot = AsyncMock()
        return store

    @pytest.fixture
    def monitor(self, mock_perf_store, mock_correlation_store):
        return CorrelationMonitor(
            perf_store=mock_perf_store,
            correlation_store=mock_correlation_store,
            config=CorrelationConfig(),
        )

    @pytest.mark.asyncio
    async def test_compute_correlation_matrix_disabled(
        self, mock_perf_store, mock_correlation_store
    ):
        config = CorrelationConfig(enabled=False)
        monitor = CorrelationMonitor(
            perf_store=mock_perf_store,
            correlation_store=mock_correlation_store,
            config=config,
        )
        result = await monitor.compute_correlation_matrix()
        assert result.alert_level == CorrelationAlertLevel.NORMAL
        assert result.agent_count == 0

    @pytest.mark.asyncio
    async def test_compute_correlation_matrix_with_agents(self, monitor):
        result = await monitor.compute_correlation_matrix()
        assert result.agent_count >= 0

    def test_should_reduce_position_no_snapshot(self, monitor):
        should_reduce, multiplier = monitor.should_reduce_position("agent_a", None)
        assert should_reduce is False
        assert multiplier == 1.0

    def test_should_reduce_position_normal(self, monitor):
        snapshot = CorrelationSnapshot(
            timestamp=datetime.now(timezone.utc),
            alert_level=CorrelationAlertLevel.NORMAL,
            portfolio_diversification_score=0.8,
            high_correlation_pairs=[],
            agent_count=2,
            analyzed_pairs=1,
            skipped_pairs=0,
        )
        should_reduce, multiplier = monitor.should_reduce_position("agent_a", snapshot)
        assert should_reduce is False
        assert multiplier == 1.0

    def test_should_reduce_position_with_high_correlation(self, monitor):
        snapshot = CorrelationSnapshot(
            timestamp=datetime.now(timezone.utc),
            alert_level=CorrelationAlertLevel.WARNING,
            portfolio_diversification_score=0.4,
            high_correlation_pairs=[
                CorrelationPair("agent_a", "agent_b", 0.85, 30, 30),
            ],
            agent_count=2,
            analyzed_pairs=1,
            skipped_pairs=0,
        )
        should_reduce, multiplier = monitor.should_reduce_position("agent_a", snapshot)
        assert should_reduce is True
        assert multiplier == 0.75

    def test_should_reduce_position_multiple_correlations(self, monitor):
        snapshot = CorrelationSnapshot(
            timestamp=datetime.now(timezone.utc),
            alert_level=CorrelationAlertLevel.CRITICAL,
            portfolio_diversification_score=0.2,
            high_correlation_pairs=[
                CorrelationPair("agent_a", "agent_b", 0.9, 30, 30),
                CorrelationPair("agent_a", "agent_c", 0.85, 30, 30),
            ],
            agent_count=3,
            analyzed_pairs=3,
            skipped_pairs=0,
        )
        should_reduce, multiplier = monitor.should_reduce_position("agent_a", snapshot)
        assert should_reduce is True
        assert multiplier == 0.5


class TestCorrelationStore:
    """Tests for CorrelationStore."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        # Mock fetchone to return None
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_cursor.fetchall = AsyncMock(return_value=[])
        db.execute.return_value = mock_cursor
        return db

    @pytest.mark.asyncio
    async def test_initialize(self, mock_db):
        store = CorrelationStore(mock_db)
        await store.initialize()
        assert mock_db.execute.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_save_snapshot(self, mock_db):
        store = CorrelationStore(mock_db)
        snapshot = CorrelationSnapshot(
            timestamp=datetime.now(timezone.utc),
            alert_level=CorrelationAlertLevel.NORMAL,
            portfolio_diversification_score=0.8,
            high_correlation_pairs=[],
            agent_count=2,
            analyzed_pairs=1,
            skipped_pairs=0,
        )
        await store.save_snapshot(snapshot)
        assert mock_db.execute.called
        assert mock_db.commit.called
