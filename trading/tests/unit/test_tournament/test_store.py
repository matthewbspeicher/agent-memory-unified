import pytest
import aiosqlite
from storage.db import init_db
from tournament.store import TournamentStore
from learning.config import LearningConfig


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


async def test_tables_exist(db):
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('tournament_audit_log', 'agent_stages')"
    )
    names = {row["name"] for row in await cursor.fetchall()}
    assert "tournament_audit_log" in names
    assert "agent_stages" in names


async def test_upsert_and_get_stage(db):
    store = TournamentStore(db)
    await store.set_stage("my_agent", 0)
    stage = await store.get_stage("my_agent")
    assert stage == 0


async def test_set_stage_updates_existing(db):
    store = TournamentStore(db)
    await store.set_stage("my_agent", 0)
    await store.set_stage("my_agent", 1)
    stage = await store.get_stage("my_agent")
    assert stage == 1


async def test_get_stage_unknown_returns_zero(db):
    store = TournamentStore(db)
    stage = await store.get_stage("unknown_agent")
    assert stage == 0


async def test_write_and_list_audit_rows(db):
    store = TournamentStore(db)
    await store.write_audit(
        agent_name="my_agent",
        from_stage=0,
        to_stage=1,
        reason="thresholds passed",
        ai_analysis="Looks good",
        ai_recommendation="go",
        overridden_by=None,
    )
    rows = await store.list_audit(limit=10)
    assert len(rows) == 1
    assert rows[0]["agent_name"] == "my_agent"
    assert rows[0]["from_stage"] == 0
    assert rows[0]["to_stage"] == 1
    assert rows[0]["ai_recommendation"] == "go"


def test_learning_config_tournament_section():
    data = {
        "pnl": {"mark_to_market_seconds": 60, "reconciliation_seconds": 300},
        "retention": {"default_days": 90},
        "optimization": {
            "grid_search_schedule": "0 2 * * 0",
            "tournament_challengers": 4,
            "tournament_promotion_margin": 0.10,
            "min_backtest_trades": 30,
            "min_paper_days": 7,
        },
        "reflection": {
            "feedback_model": "claude-sonnet-4-20250514",
            "synthesis_model": "claude-sonnet-4-20250514",
            "synthesis_interval_days": 7,
            "max_learned_rules": 10,
            "recent_lessons_window": 5,
            "auto_revert_sharpe_drop": 0.20,
        },
        "guardrails": {
            "max_daily_parameter_changes": 1,
            "max_parameter_change_pct": 0.20,
            "cooldown_after_disable_hours": 48,
        },
        "tournament": {
            "enabled": True,
            "evaluate_cron": "0 * * * *",
            "stages": {
                1: {
                    "min_sharpe": 1.5,
                    "min_trades": 50,
                    "max_drawdown": 0.15,
                    "min_win_rate": 0.45,
                },
                2: {
                    "min_sharpe": 1.8,
                    "min_trades": 100,
                    "max_drawdown": 0.12,
                    "min_win_rate": 0.48,
                },
                3: {
                    "min_sharpe": 2.0,
                    "min_trades": 200,
                    "max_drawdown": 0.10,
                    "min_win_rate": 0.50,
                },
            },
            "live_limited": {"max_capital_pct": 0.10, "max_capital_usd": 500},
        },
    }
    cfg = LearningConfig(**data)
    assert cfg.tournament.enabled is True
    assert cfg.tournament.stages[1].min_sharpe == 1.5
    assert cfg.tournament.stages[3].min_trades == 200
    assert cfg.tournament.live_limited.max_capital_usd == 500
