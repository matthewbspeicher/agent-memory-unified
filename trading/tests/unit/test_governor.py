import pytest
from unittest.mock import MagicMock, AsyncMock
from decimal import Decimal
from risk.governor import CapitalGovernor
from risk.rules import PortfolioContext
from broker.models import Symbol, AssetType, Quote, MarketOrder


@pytest.fixture
def mock_leaderboard():
    return MagicMock()


@pytest.fixture
def mock_tournament():
    return MagicMock()


@pytest.fixture
def mock_perf_store():
    m = AsyncMock()
    m.get_latest.return_value.daily_pnl_pct = 0.0
    return m


@pytest.fixture
def mock_agent_store():
    return AsyncMock()


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.governor_cache_ttl_secs = 300
    settings.governor_min_sharpe_promotion = 1.5
    return settings


@pytest.mark.asyncio
async def test_governor_size_factor(
    mock_leaderboard, mock_tournament, mock_perf_store, mock_agent_store, mock_settings
):
    # Setup
    governor = CapitalGovernor(
        leaderboard=mock_leaderboard,
        tournament=mock_tournament,
        perf_store=mock_perf_store,
        agent_store=mock_agent_store,
        settings=mock_settings,
    )

    # Mock data
    agent_name = "test_agent"
    mock_ranking = MagicMock()
    mock_ranking.agent_name = agent_name
    mock_ranking.sharpe_ratio = 1.5  # On target

    mock_leaderboard.get_cached_leaderboard = AsyncMock(return_value=[mock_ranking])
    mock_tournament.get_all_stages = AsyncMock(
        return_value={agent_name: 3}
    )  # Stage 3 (Max)

    # Warm cache
    await governor._refresh_cache_if_needed()

    # Evaluate
    symbol = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
    trade = MarketOrder(
        symbol=symbol, side="BUY", quantity=Decimal("100"), account_id="TEST"
    )
    trade.agent_name = agent_name
    quote = Quote(symbol=symbol, last=Decimal("150.0"))
    ctx = PortfolioContext(positions=[], balance=MagicMock())

    result = await governor.evaluate(trade, quote, ctx)

    assert result.passed
    # Sharpe Target (1.0) * Stage Ratio (1.0) = 1.0 factor
    assert result.adjusted_quantity == Decimal("100")


@pytest.mark.asyncio
async def test_governor_demotion(
    mock_leaderboard, mock_tournament, mock_perf_store, mock_agent_store, mock_settings
):
    governor = CapitalGovernor(
        mock_leaderboard,
        mock_tournament,
        mock_perf_store,
        mock_agent_store,
        mock_settings,
    )

    agent_name = "bad_agent"
    mock_ranking = MagicMock()
    mock_ranking.agent_name = agent_name
    mock_ranking.sharpe_ratio = -2.0  # Way below threshold

    mock_leaderboard.get_cached_leaderboard = AsyncMock(return_value=[mock_ranking])
    mock_tournament.get_all_stages = AsyncMock(return_value={agent_name: 1})

    await governor._refresh_cache_if_needed()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side="BUY",
        quantity=Decimal("100"),
        account_id="TEST",
    )
    trade.agent_name = agent_name
    result = await governor.evaluate(
        trade, MagicMock(), PortfolioContext([], MagicMock())
    )

    assert not result.passed
    assert "demoted" in result.reason
