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

from integrations.bittensor.models import MinerAccuracyRecord, MinerRanking
from storage.bittensor import BittensorStore
from storage.db import init_db_postgres
from storage.postgres import PostgresDB
from storage.trade_analytics import TradeAnalyticsStore

pytestmark = pytest.mark.integration

_SCRIPT = (Path(__file__).parents[3] / "scripts" / "init-trading-tables.sql").read_text()
NOW = datetime.now(timezone.utc)
TABLES = ("bittensor_accuracy_records", "bittensor_miner_rankings", "trade_analytics")


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
    assert float(rollup["miner-a"]["direction_accuracy"]) == 0.0
    assert float(rollup["miner-b"]["direction_accuracy"]) == 1.0


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


async def test_a_table_that_still_has_its_older_key_keeps_working(schema, caplog):
    """Rankings were once keyed by miner alone; a live table may still be."""
    async with schema.acquire() as connection:
        older = script_table("bittensor_miner_rankings").replace(
            "PRIMARY KEY (miner_hotkey, symbol)", "PRIMARY KEY (miner_hotkey)"
        )
        assert "PRIMARY KEY (miner_hotkey)" in older
        await connection.execute(older)
    store = BittensorStore(PostgresDB(schema))
    with caplog.at_level(logging.WARNING, logger="storage.postgres"):
        await store.update_miner_ranking(MinerRanking("miner-a", hybrid_score=0.4))
        await store.update_miner_ranking(MinerRanking("miner-a", hybrid_score=0.9))
    rankings = await store.get_miner_rankings()
    assert [(r.miner_hotkey, r.hybrid_score) for r in rankings] == [
        ("miner-a", pytest.approx(0.9))
    ]
    # Reported once, then the older key is used directly.
    warnings = [r for r in caplog.records if "unique key differs" in r.getMessage()]
    assert len(warnings) == 1
