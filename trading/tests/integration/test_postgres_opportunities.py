"""Opportunity storage and approval against a disposable PostgreSQL schema.

Two table definitions exist for PostgreSQL: the bootstrap script's (TIMESTAMP
and JSONB columns) and the engine's own (TEXT columns). The store must work
with both, in a session whose time zone is not UTC.
"""

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from agents.approval import ApprovalRefused, OpportunityApprover
from agents.models import Opportunity, OpportunityStatus
from broker.models import TIF, AssetType, LimitOrder, OrderSide, Symbol
from storage.opportunities import REVISION_KEY, OpportunityStore
from storage.postgres import PostgresDB

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).parents[3] / "scripts" / "init-trading-tables.sql"
TEXT_COLUMNS = """
CREATE TABLE opportunities (
    id TEXT PRIMARY KEY, agent_name TEXT NOT NULL, symbol TEXT NOT NULL,
    signal TEXT NOT NULL, confidence REAL NOT NULL, reasoning TEXT NOT NULL,
    suggested_trade TEXT, status TEXT NOT NULL DEFAULT 'pending',
    expires_at TEXT, data TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
)"""


def script_columns() -> str:
    return re.search(
        r"CREATE TABLE IF NOT EXISTS opportunities \(.*?\);", _SCRIPT.read_text(), re.S
    ).group(0)


@pytest.fixture(params=["script", "text"])
async def store(request):
    dsn = os.environ.get("AMU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail("AMU_TEST_POSTGRES_DSN must identify a disposable test database")
    schema = "opportunities_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=4,
        server_settings={"search_path": schema, "timezone": "Asia/Tokyo"},
    )
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                script_columns() if request.param == "script" else TEXT_COLUMNS
            )
        yield OpportunityStore(PostgresDB(pool))
    finally:
        await pool.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


SYMBOL = Symbol("KXTEST", AssetType.PREDICTION)


def opportunity(expires_at=None):
    return Opportunity(
        id="opp-1",
        agent_name="suggester",
        symbol=SYMBOL,
        signal="MISPRICED",
        confidence=0.8,
        reasoning="test",
        data={"edge": 0.07},
        timestamp=datetime.now(timezone.utc),
        suggested_trade=LimitOrder(
            SYMBOL,
            OrderSide.BUY,
            Decimal("5"),
            "KALSHI_PAPER",
            TIF.GTC,
            limit_price=0.57,
        ),
        expires_at=expires_at,
        broker_id="kalshi_paper",
    )


class Router:
    def __init__(self, store):
        self.store, self.executed = store, 0

    async def execute(self, opportunity, *, max_quantity=None):
        self.executed += 1
        await asyncio.sleep(0.05)
        await self.store.update_status(opportunity.id, OpportunityStatus.EXECUTED)


def approver(store, router):
    return OpportunityApprover(store, router, max_age=timedelta(minutes=60))


async def test_expiry_round_trips_as_the_same_instant(store):
    tokyo = timezone(timedelta(hours=9))
    expiry = datetime(2026, 11, 12, 21, 30, tzinfo=tokyo)
    assert await store.save(opportunity(expires_at=expiry)) is True
    assert (await store.load("opp-1")).expires_at == expiry
    # A second save reuses what the first learned about the column.
    assert await store.save(opportunity(expires_at=expiry)) is True
    assert (await store.load("opp-1")).expires_at == expiry


async def test_stored_order_and_offer_survive(store):
    await store.save(opportunity())
    await store.mark_approvable(
        "opp-1", revision=(await store.load("opp-1")).data[REVISION_KEY]
    )
    loaded = await store.load("opp-1")
    assert loaded.suggested_trade.limit_price == Decimal("0.57")
    assert loaded.broker_id == "kalshi_paper"
    offered = await store.offered_at("opp-1")
    assert abs(datetime.now(timezone.utc) - offered) < timedelta(minutes=1)


async def test_simultaneous_approvals_place_one_order(store):
    await store.save(opportunity())
    await store.mark_approvable(
        "opp-1", revision=(await store.load("opp-1")).data[REVISION_KEY]
    )
    router = Router(store)
    results = await asyncio.gather(
        *(approver(store, router).approve("opp-1") for _ in range(3)),
        return_exceptions=True,
    )
    assert router.executed == 1
    assert sum(isinstance(r, ApprovalRefused) for r in results) == 2
    assert (await store.get("opp-1"))["status"] == "executed"
    assert await store.save(opportunity()) is False


async def test_approval_past_expiry_is_refused(store):
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await store.save(opportunity(expires_at=past))
    await store.mark_approvable(
        "opp-1", revision=(await store.load("opp-1")).data[REVISION_KEY]
    )
    router = Router(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "expired"
    assert router.executed == 0
    assert (await store.get("opp-1"))["status"] == "expired"


async def test_approval_before_expiry_executes(store):
    soon = datetime.now(timezone.utc) + timedelta(minutes=30)
    await store.save(opportunity(expires_at=soon))
    await store.mark_approvable(
        "opp-1", revision=(await store.load("opp-1")).data[REVISION_KEY]
    )
    outcome = await approver(store, Router(store)).approve("opp-1")
    assert outcome.status == OpportunityStatus.EXECUTED


async def test_listing_by_minimum_age_leaves_out_newer_opportunities(store):
    """Explorer-tier listings are delayed by an hour."""
    for name, age in (("old", "-2 hours"), ("recent", "-30 minutes"), ("new", None)):
        saved = opportunity()
        saved.id = name
        await store.save(saved)
        if age:
            await store._db.execute(
                f"UPDATE opportunities SET created_at = datetime('now', '{age}')"
                " WHERE id = ?",
                (name,),
            )
    assert [row["id"] for row in await store.list(min_age_hours=1)] == ["old"]
    assert len(await store.list()) == 3
