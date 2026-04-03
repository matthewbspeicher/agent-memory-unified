import pytest
import aiosqlite

from learning.tournament import TournamentRunner
from storage.db import init_db


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        yield conn


@pytest.fixture
async def runner(db):
    return TournamentRunner(db)


@pytest.mark.asyncio
async def test_start_round(runner):
    champion_params = {"rsi_threshold": 30, "lookback": 14}
    challenger_params_list = [{"rsi_threshold": 25, "lookback": 10}]

    round_id = await runner.start_round(
        agent_name="test_agent",
        champion_params=champion_params,
        challenger_params_list=challenger_params_list,
    )

    assert round_id is not None

    round_data = await runner.get_round(round_id)
    assert round_data is not None
    assert round_data["status"] == "running"
    assert round_data["agent_name"] == "test_agent"
    assert round_data["champion_params"] == champion_params


@pytest.mark.asyncio
async def test_record_variant_result(runner):
    champion_params = {"rsi_threshold": 30}
    challenger_params_list = [{"rsi_threshold": 25}]

    round_id = await runner.start_round(
        agent_name="test_agent",
        champion_params=champion_params,
        challenger_params_list=challenger_params_list,
    )

    variants = await runner.get_variants(round_id)
    assert len(variants) == 2

    champion_variant = variants[0]
    assert champion_variant["variant_label"] == "champion"
    assert champion_variant["parameters"] == champion_params

    await runner.update_variant(
        champion_variant["id"],
        sharpe_ratio=1.2,
        profit_factor=1.8,
        total_pnl="5000.00",
        total_trades=40,
    )

    updated_variants = await runner.get_variants(round_id)
    updated_champion = updated_variants[0]
    assert updated_champion["sharpe_ratio"] == 1.2
    assert updated_champion["profit_factor"] == 1.8
    assert updated_champion["total_pnl"] == "5000.00"
    assert updated_champion["total_trades"] == 40


@pytest.mark.asyncio
async def test_complete_round_with_winner(runner):
    round_id = await runner.start_round(
        agent_name="test_agent",
        champion_params={"rsi_threshold": 30},
        challenger_params_list=[{"rsi_threshold": 25}],
    )

    variants = await runner.get_variants(round_id)
    champion_variant = variants[0]
    challenger_variant = variants[1]

    # Champion sharpe=1.0, challenger sharpe=1.5 (50% better, margin=10%)
    await runner.update_variant(
        champion_variant["id"],
        sharpe_ratio=1.0,
        profit_factor=1.5,
        total_pnl="3000.00",
        total_trades=50,
    )
    await runner.update_variant(
        challenger_variant["id"],
        sharpe_ratio=1.5,
        profit_factor=2.0,
        total_pnl="6000.00",
        total_trades=50,
    )

    winner = await runner.complete_round(round_id, promotion_margin=0.10, min_trades=30)

    assert winner is not None
    assert winner["variant_label"] == "challenger_0"
    assert winner["sharpe_ratio"] == 1.5

    round_data = await runner.get_round(round_id)
    assert round_data["status"] == "completed"
    assert round_data["winner_sharpe"] == 1.5


@pytest.mark.asyncio
async def test_no_winner_when_margin_not_met(runner):
    round_id = await runner.start_round(
        agent_name="test_agent",
        champion_params={"rsi_threshold": 30},
        challenger_params_list=[{"rsi_threshold": 35}],
    )

    variants = await runner.get_variants(round_id)
    champion_variant = variants[0]
    challenger_variant = variants[1]

    # Champion sharpe=1.5, challenger sharpe=1.55 (3.3% better, margin=10%)
    await runner.update_variant(
        champion_variant["id"],
        sharpe_ratio=1.5,
        profit_factor=2.0,
        total_pnl="5000.00",
        total_trades=50,
    )
    await runner.update_variant(
        challenger_variant["id"],
        sharpe_ratio=1.55,
        profit_factor=2.1,
        total_pnl="5200.00",
        total_trades=50,
    )

    winner = await runner.complete_round(round_id, promotion_margin=0.10, min_trades=30)

    assert winner is None

    round_data = await runner.get_round(round_id)
    assert round_data["status"] == "completed"
    assert round_data["winner_params"] is None
    assert round_data["winner_sharpe"] is None
