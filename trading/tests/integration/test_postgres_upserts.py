"""INSERT OR REPLACE through the PostgreSQL facade, on a disposable schema.

A wrong conflict key is only rejected when the statement runs, so this has to
be exercised against a real server: on the engine's own schema, on the
bootstrap script's, and on a table that still has an older key.
"""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from unittest.mock import MagicMock

from integrations.bittensor.models import (
    MinerAccuracyRecord,
    MinerRanking,
    RawMinerForecast,
)
from integrations.bittensor.evaluator import MinerEvaluator
from storage.bittensor import BittensorStore
from storage.db import init_db_postgres
from storage.postgres import PostgresDB
from storage.trade_analytics import TradeAnalyticsStore

pytestmark = pytest.mark.integration

_SCRIPT = (Path(__file__).parents[3] / "scripts" / "init-trading-tables.sql").read_text()
NOW = datetime.now(timezone.utc)
TABLES = (
    "bittensor_accuracy_records",
    "bittensor_miner_rankings",
    "bittensor_raw_forecasts",
    "trade_analytics",
)


def script_table(name: str) -> str:
    return re.search(
        rf"CREATE TABLE IF NOT EXISTS {name} \(.*?\);", _SCRIPT, re.S
    ).group(0)


@pytest.fixture
async def schema():
    dsn = os.environ.get("AMU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail("AMU_TEST_POSTGRES_DSN must identify a disposable test database")
    name = "upserts_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE SCHEMA "{name}"')
    pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=4,
        statement_cache_size=0,
        server_settings={"search_path": name},
    )
    try:
        yield pool
    finally:
        await pool.close()
        await admin.execute(f'DROP SCHEMA "{name}" CASCADE')
        await admin.close()


@pytest.fixture(params=["engine", "script"])
async def db(request, schema):
    facade = PostgresDB(schema)
    if request.param == "engine":
        await init_db_postgres(facade)
    else:
        async with schema.acquire() as connection:
            for table in TABLES:
                await connection.execute(script_table(table))
    return facade


def accuracy(miner, correct):
    return MinerAccuracyRecord(
        window_id="w1",
        miner_hotkey=miner,
        symbol="BTCUSD",
        timeframe="5m",
        direction_correct=correct,
        predicted_return=0.01,
        actual_return=0.02,
        magnitude_error=0.01,
        path_correlation=0.5,
        outcome_bars=100,
        scoring_version="v1",
        evaluated_at=NOW,
    )


async def test_accuracy_records_are_kept_per_miner_and_replaced_on_rescoring(db):
    store = BittensorStore(db)
    await store.save_accuracy_records([accuracy("miner-a", True), accuracy("miner-b", True)])
    await store.save_accuracy_records([accuracy("miner-a", False)])
    records = {r.miner_hotkey: r for r in await store.get_accuracy_for_window("w1")}
    assert sorted(records) == ["miner-a", "miner-b"]
    assert bool(records["miner-a"].direction_correct) is False
    assert bool(records["miner-b"].direction_correct) is True
    # The rollup that rankings are computed from averages the same column.
    rollup = await store.get_accuracy_rollup(["miner-a", "miner-b"], lookback=10)
    assert rollup["miner-a"]["direction_accuracy"] == 0.0
    assert rollup["miner-b"]["direction_accuracy"] == 1.0
    # Floats, not the Decimal a NUMERIC column returns: scoring multiplies them.
    numbers = [
        rollup["miner-a"]["direction_accuracy"],
        rollup["miner-a"]["mean_magnitude_error"],
        rollup["miner-a"]["mean_path_correlation"],
        records["miner-a"].predicted_return,
        records["miner-a"].magnitude_error,
        records["miner-a"].path_correlation,
    ]
    assert [type(n) for n in numbers] == [float] * len(numbers)


async def test_miner_rankings_are_kept_per_symbol_and_replaced_on_update(db):
    store = BittensorStore(db)
    await store.update_miner_ranking(MinerRanking("miner-a", "BTCUSD", hybrid_score=0.4))
    await store.update_miner_ranking(MinerRanking("miner-a", "ETHUSD", hybrid_score=0.7))
    await store.update_miner_ranking(MinerRanking("miner-a", "BTCUSD", hybrid_score=0.9))
    btc = await store.get_miner_rankings(symbol="BTCUSD")
    eth = await store.get_miner_rankings(symbol="ETHUSD")
    assert [(r.miner_hotkey, r.hybrid_score) for r in btc] == [("miner-a", pytest.approx(0.9))]
    assert [(r.miner_hotkey, r.hybrid_score) for r in eth] == [("miner-a", pytest.approx(0.7))]
    assert isinstance(btc[0].hybrid_score, float)


async def test_trade_analytics_replace_on_the_position_whatever_column_comes_first(db):
    store = TradeAnalyticsStore(db)
    row = dict(
        agent_name="agent",
        symbol="AAPL",
        side="buy",
        entry_time=NOW.isoformat(),
        exit_time=NOW.isoformat(),
        hold_minutes=5.0,
        entry_price="100",
        exit_price="101",
        entry_quantity=1,
        entry_fees="0",
        exit_fees="0",
        gross_pnl="1",
        gross_return_pct=1.0,
        net_return_pct=1.0,
        realized_outcome="win",
    )
    await store.upsert(tracked_position_id=7, **row, net_pnl="1.5")
    await store.upsert(tracked_position_id=7, **row, net_pnl="2.5")
    await store.upsert(tracked_position_id=8, **row, net_pnl="9")
    assert float((await store.get(7))["net_pnl"]) == 2.5
    assert len(await store.list_all()) == 2


async def older_rankings_table(schema):
    """Rankings were once keyed by miner alone; a live table may still be."""
    async with schema.acquire() as connection:
        older = script_table("bittensor_miner_rankings").replace(
            "PRIMARY KEY (miner_hotkey, symbol)", "PRIMARY KEY (miner_hotkey)"
        )
        assert "PRIMARY KEY (miner_hotkey)" in older
        await connection.execute(older)
        for table in ("bittensor_accuracy_records", "bittensor_raw_forecasts"):
            await connection.execute(script_table(table))
    return BittensorStore(PostgresDB(schema))


async def test_a_table_that_still_has_its_older_key_keeps_working(schema, caplog):
    store = await older_rankings_table(schema)
    with caplog.at_level(logging.WARNING):
        await store.update_miner_ranking(MinerRanking("miner-a", hybrid_score=0.4))
        await store.update_miner_ranking(MinerRanking("miner-a", hybrid_score=0.9))
    rankings = await store.get_miner_rankings()
    assert [(r.miner_hotkey, r.hybrid_score) for r in rankings] == [
        ("miner-a", pytest.approx(0.9))
    ]
    # The older key is reported once, then used directly.
    warnings = [r for r in caplog.records if "unique key differs" in r.getMessage()]
    assert len(warnings) == 1


async def test_an_older_table_keeps_every_miners_aggregate_ranking(schema, caplog):
    """A per-symbol ranking would overwrite the miner's only row, and a reader
    in the middle of a refresh would find that miner's aggregate missing."""
    store = await older_rankings_table(schema)
    with caplog.at_level(logging.WARNING, logger="storage.bittensor"):
        for miner in ("miner-a", "miner-b"):
            await store.update_miner_ranking(MinerRanking(miner, hybrid_score=0.5))
        # The start of the next refresh: one miner's symbol ranking arrives.
        await store.update_miner_ranking(MinerRanking("miner-a", "BTCUSD", hybrid_score=0.1))
        aggregate = await store.get_miner_rankings(symbol="aggregate")
    assert sorted(r.miner_hotkey for r in aggregate) == ["miner-a", "miner-b"]
    assert await store.get_miner_rankings(symbol="BTCUSD") == []
    said = [r for r in caplog.records if "keyed by miner alone" in r.getMessage()]
    assert len(said) == 1


async def test_a_ranking_refresh_on_an_older_table_ranks_every_miner(schema):
    store = await older_rankings_table(schema)
    await seed_two_miners(store)
    await MinerEvaluator(store=store, data_bus=MagicMock()).refresh_rankings()
    await MinerEvaluator(store=store, data_bus=MagicMock()).refresh_rankings()
    aggregate = await store.get_miner_rankings(symbol="aggregate")
    assert sorted(r.miner_hotkey for r in aggregate) == ["miner-a", "miner-b"]
    assert len(await store.get_miner_rankings()) == 2


def forecast(miner, window, incentive):
    return RawMinerForecast(
        window_id=window,
        request_uuid=uuid4().hex,
        collected_at=NOW,
        miner_uid=1,
        miner_hotkey=miner,
        stream_id="s",
        topic_id=1,
        schema_id=1,
        symbol="BTCUSD",
        timeframe="5m",
        feature_ids=[1],
        prediction_size=2,
        predictions=[1.0, 2.0],
        hashed_predictions=None,
        hash_verified=True,
        incentive_score=incentive,
        vtrust=0.9,
        stake_tao=12.5,
    )


async def test_incentive_scores_are_read_per_miner_as_floats(db):
    """They are half of a miner's ranking. Read by position they were all zero."""
    store = BittensorStore(db)
    await store.save_raw_forecasts(
        [forecast("miner-a", "w1", 0.25), forecast("miner-b", "w1", 0.75)]
    )
    scores = await store.get_latest_incentive_scores(["miner-a", "miner-b", "miner-c"])
    assert scores == {"miner-a": pytest.approx(0.25), "miner-b": pytest.approx(0.75)}
    assert all(type(score) is float for score in scores.values())
    stored = (await store.get_raw_forecasts_by_window("w1"))[0]
    assert [type(v) for v in (stored.incentive_score, stored.vtrust, stored.stake_tao)] == [float] * 3


async def seed_two_miners(store):
    """Six windows each: miner-a is always right, miner-b has the incentive."""
    records, forecasts = [], []
    for window in range(6):
        for miner, correct, incentive in (("miner-a", True, 0.1), ("miner-b", False, 0.9)):
            record = accuracy(miner, correct)
            record.window_id = f"w{window}"
            records.append(record)
            forecasts.append(forecast(miner, f"w{window}", incentive))
    await store.save_accuracy_records(records)
    await store.save_raw_forecasts(forecasts)


async def test_a_ranking_refresh_stores_one_scored_ranking_per_miner(db):
    """The whole path that produces the rankings weights are set from."""
    store = BittensorStore(db)
    await seed_two_miners(store)

    await MinerEvaluator(store=store, data_bus=MagicMock()).refresh_rankings()

    rankings = {r.miner_hotkey: r for r in await store.get_miner_rankings(symbol="aggregate")}
    assert sorted(rankings) == ["miner-a", "miner-b"]
    accurate, favoured = rankings["miner-a"], rankings["miner-b"]
    assert accurate.windows_evaluated == 6
    assert accurate.direction_accuracy == 1.0 and favoured.direction_accuracy == 0.0
    # The incentive scores reached the ranking; read by position they were lost.
    assert favoured.latest_incentive_score > accurate.latest_incentive_score
    assert accurate.hybrid_score != favoured.hybrid_score
    assert type(accurate.hybrid_score) is float
    # Each symbol has its own rankings beside the aggregate.
    assert len(await store.get_miner_rankings(symbol="BTCUSD")) == 2
    # A second refresh replaces the rankings instead of failing or duplicating.
    await MinerEvaluator(store=store, data_bus=MagicMock()).refresh_rankings()
    assert len(await store.get_miner_rankings(symbol="aggregate")) == 2
