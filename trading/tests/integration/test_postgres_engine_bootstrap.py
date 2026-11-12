"""The engine must be able to create its own tables on an empty PostgreSQL.

`init_db_postgres` runs the engine's DDL as one script. A single statement
PostgreSQL rejects rolls the whole script back, and the error is only logged,
so the engine used to start against an empty database with no tables at all.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest

from agents.models import Opportunity
from broker.models import TIF, AssetType, LimitOrder, OrderSide, Symbol
from execution.models import ArbState
from storage.arbitrage import ArbStore
from storage.consensus import ConsensusStore
from storage.db import init_db_postgres
from storage.opportunities import OpportunityStore
from storage.performance import PerformanceSnapshot, PerformanceStore
from storage.postgres import PostgresDB
from storage.spreads import SpreadObservation, SpreadStore
from storage.strategy_health import StrategyHealthStore

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)
CORE_TABLES = {
    "opportunities",
    "trade_executions",
    "tracked_positions",
    "performance_snapshots",
    "consensus_votes",
    "strategy_health",
    "arb_spread_observations",
    "arb_trades",
    "shadow_executions",
}


@pytest.fixture
async def empty():
    dsn = os.environ.get("AMU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail("AMU_TEST_POSTGRES_DSN must identify a disposable test database")
    schema = "bootstrap_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=4,
        statement_cache_size=0,
        server_settings={"search_path": schema},
    )
    try:
        yield PostgresDB(pool), schema, admin
    finally:
        await pool.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


async def tables(admin, schema):
    rows = await admin.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = $1",
        schema,
    )
    return {row["table_name"] for row in rows}


async def test_engine_creates_its_tables_on_an_empty_database(empty, caplog):
    db, schema, admin = empty
    assert await tables(admin, schema) == set()
    with caplog.at_level(logging.WARNING, logger="storage.db"):
        await init_db_postgres(db)
        created = await tables(admin, schema)
        await init_db_postgres(db)  # every start runs it again
    assert [r.getMessage() for r in caplog.records] == []
    assert CORE_TABLES <= created
    assert await tables(admin, schema) == created


async def test_core_stores_work_on_the_schema_the_engine_creates(empty):
    db, _, _ = empty
    await init_db_postgres(db)
    symbol = Symbol("KXTEST", AssetType.PREDICTION)
    expiry = NOW + timedelta(minutes=30)

    opportunities = OpportunityStore(db)
    assert await opportunities.save(
        Opportunity(
            id="opp-1",
            agent_name="agent",
            symbol=symbol,
            signal="MISPRICED",
            confidence=0.8,
            reasoning="test",
            data={},
            timestamp=NOW,
            suggested_trade=LimitOrder(
                symbol,
                OrderSide.BUY,
                Decimal("5"),
                "KALSHI_PAPER",
                TIF.GTC,
                limit_price=Decimal("0.57"),
            ),
            expires_at=expiry,
        )
    )
    loaded = await opportunities.load("opp-1")
    assert loaded.expires_at == expiry
    assert loaded.suggested_trade.limit_price == Decimal("0.57")

    performance = PerformanceStore(db)
    await performance.save(
        PerformanceSnapshot(
            agent_name="agent",
            timestamp=NOW,
            opportunities_generated=1,
            opportunities_executed=1,
            win_rate=0.5,
            total_pnl=Decimal("12.5"),
        )
    )
    assert (await performance.get_latest("agent")).timestamp == NOW

    votes = ConsensusStore(db)
    await votes.add_vote("AAPL", "buy", "agent", "opp-1", NOW)
    assert len(await votes.get_votes("AAPL", "buy", NOW - timedelta(hours=1))) == 1

    health = StrategyHealthStore(db)
    await health.upsert_status("agent", "healthy", cooldown_until=NOW.isoformat())
    assert (await health.get_status("agent"))["status"] == "healthy"

    # A datetime bound to a time column the engine declares as text.
    await ArbStore(db).update_trade_state("no-such-trade", ArbState.FAILED)


async def test_a_spread_can_be_recorded_found_and_claimed_once(empty):
    """This is the table whose definition stopped every table being created."""
    db, _, _ = empty
    await init_db_postgres(db)
    spreads = SpreadStore(db)
    observation = await spreads.record(SpreadObservation("KX", "POLY", 0.9, 50, 58, 8))
    assert observation is not None
    assert (await spreads.get_observation(observation))["gap_cents"] == 8
    assert [s["id"] for s in await spreads.get_top_spreads(min_gap=1)] == [observation]
    assert await spreads.claim_spread(observation, "first") is True
    assert await spreads.claim_spread(observation, "second") is False
    assert await spreads.get_top_spreads(min_gap=1) == []
    await spreads.release_spread(observation)
    assert await spreads.claim_spread(observation, "second") is True
