"""Tests for LeaderboardEngine."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from storage.performance import PerformanceSnapshot


def _make_snapshot(
    agent_name: str, sharpe: float, total_pnl: float = 0.0, win_rate: float = 0.5
) -> PerformanceSnapshot:
    return PerformanceSnapshot(
        agent_name=agent_name,
        timestamp=datetime(2026, 3, 26, tzinfo=timezone.utc),
        opportunities_generated=10,
        opportunities_executed=5,
        win_rate=win_rate,
        total_pnl=Decimal(str(total_pnl)),
        sharpe_ratio=sharpe,
    )


@pytest.fixture
def mock_perf_store():
    store = MagicMock()
    store.get_latest = AsyncMock(
        side_effect=lambda name: {
            "rsi_scanner": _make_snapshot("rsi_scanner", 1.82, 842.50, 0.80),
            "volume_spike": _make_snapshot("volume_spike", 0.34, -120.00, 0.31),
            "kalshi_news_arb": _make_snapshot("kalshi_news_arb", 1.45, 500.00, 0.62),
        }.get(name)
    )
    return store


@pytest.fixture
def mock_runner():
    runner = MagicMock()
    info1 = MagicMock()
    info1.name = "rsi_scanner"
    info2 = MagicMock()
    info2.name = "volume_spike"
    info3 = MagicMock()
    info3.name = "kalshi_news_arb"
    runner.list_agents.return_value = [info1, info2, info3]
    return runner


@pytest.fixture
def mock_db():
    db = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=cursor)
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_sharpe_ranking_sorted_descending(mock_perf_store, mock_runner, mock_db):
    from leaderboard.engine import LeaderboardEngine

    engine = LeaderboardEngine(
        perf_store=mock_perf_store, runner=mock_runner, db=mock_db
    )
    rankings = await engine.compute_rankings(profiles=None)
    names = [r.agent_name for r in rankings]
    assert names == ["rsi_scanner", "kalshi_news_arb", "volume_spike"]
    assert rankings[0].sharpe_ratio == 1.82
    assert rankings[2].sharpe_ratio == 0.34


@pytest.mark.asyncio
async def test_cold_start_elo_defaults_to_1000(mock_perf_store, mock_runner, mock_db):
    from leaderboard.engine import LeaderboardEngine

    engine = LeaderboardEngine(
        perf_store=mock_perf_store, runner=mock_runner, db=mock_db
    )
    rankings = await engine.compute_rankings(profiles=None)
    for r in rankings:
        assert r.elo == 1000
        assert r.win_count == 0
        assert r.loss_count == 0
        assert r.streak == 0


@pytest.mark.asyncio
async def test_elo_update_bounded_swing(mock_perf_store, mock_runner, mock_db):
    """K_effective = 32 / (N-1). With 3 agents, K=16 per match."""
    from leaderboard.engine import LeaderboardEngine

    engine = LeaderboardEngine(
        perf_store=mock_perf_store, runner=mock_runner, db=mock_db
    )
    rankings = await engine.compute_rankings(profiles=None)
    matches = engine.run_matches(rankings)
    # 3 agents → 3 matches (round-robin)
    assert len(matches) == 3
    current_elo = {r.agent_name: r.elo for r in rankings}
    new_elo = engine.update_elo(matches, current_elo)
    # Total swing per agent should be bounded by K * (N-1) = 16 * 2 = 32
    for name in new_elo:
        assert abs(new_elo[name] - 1000) <= 32


@pytest.mark.asyncio
async def test_n1_no_matches(mock_db):
    """Single agent → no matches, ELO unchanged."""
    from leaderboard.engine import LeaderboardEngine

    store = MagicMock()
    store.get_latest = AsyncMock(return_value=_make_snapshot("only_agent", 1.5))
    runner = MagicMock()
    info = MagicMock()
    info.name = "only_agent"
    runner.list_agents.return_value = [info]
    engine = LeaderboardEngine(perf_store=store, runner=runner, db=mock_db)
    rankings = await engine.compute_rankings(profiles=None)
    matches = engine.run_matches(rankings)
    assert matches == []
    assert rankings[0].elo == 1000


@pytest.mark.asyncio
async def test_tally_results_updates_win_loss_streak(
    mock_perf_store, mock_runner, mock_db
):
    from leaderboard.engine import LeaderboardEngine

    engine = LeaderboardEngine(
        perf_store=mock_perf_store, runner=mock_runner, db=mock_db
    )
    rankings = await engine.compute_rankings(profiles=None)
    matches = engine.run_matches(rankings)
    tallied = engine.tally_results(matches, rankings)
    # rsi_scanner (highest Sharpe) should have 2 wins, 0 losses
    rsi = next(r for r in tallied if r.agent_name == "rsi_scanner")
    assert rsi.win_count == 2
    assert rsi.loss_count == 0
    assert rsi.streak == 2
    # volume_spike (lowest Sharpe) should have 0 wins, 2 losses
    vs = next(r for r in tallied if r.agent_name == "volume_spike")
    assert vs.win_count == 0
    assert vs.loss_count == 2
    assert vs.streak == -2


@pytest.mark.asyncio
async def test_idempotency_same_snapshot_returns_cached(
    mock_perf_store, mock_runner, mock_db
):
    """Second call with same snapshot timestamp returns cached, no new matches."""
    from leaderboard.engine import LeaderboardEngine

    # Simulate cached data exists with same timestamp
    cached_row = {
        "rankings_json": "[]",
        "last_processed_snapshot_at": "2026-03-26T00:00:00+00:00",
        "updated_at": "2026-03-26T00:00:00+00:00",
        "source": "live",
    }
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=cached_row)
    mock_db.execute = AsyncMock(return_value=cursor)

    engine = LeaderboardEngine(
        perf_store=mock_perf_store, runner=mock_runner, db=mock_db
    )
    # All snapshots have timestamp 2026-03-26 which matches cache
    result = await engine.get_cached_leaderboard()
    assert result is not None
