"""Storage certification against disposable real databases, without execution.

AMU_TEST_POSTGRES_DSN must point at a disposable PostgreSQL database. Each
PostgreSQL case owns a private schema; SQLite cases own a temporary file.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from uuid import uuid4

import pytest

from agents.models import Opportunity
from broker.models import Symbol
from config import Config
from execution.fill_reconciliation import PaperFillReconciler
from execution.paper_driver import PaperMatchingDriver
from exits.manager import ExitManager
from storage.exit_rules import ExitRuleStore
from storage.opportunities import OpportunityStore, REVISION_KEY
from storage.paper import PaperStore
from storage.pnl import TrackedPositionStore
from storage.postgres import PostgresDB
from storage.readiness import StorageSession, StorageUnavailable
from storage.trades import TradeStore

pytestmark = pytest.mark.integration


@pytest.fixture(params=("sqlite", "postgres"))
async def storage_config(request, tmp_path, monkeypatch):
    options = {
        "paper_trading": False,
        "worker_mode": False,
        "paper_matching_enabled": False,
        "paper_trading_initial_balance": 12345.0,
    }
    if request.param == "sqlite":
        yield Config(db_path=str(tmp_path / "storage.db"), **options)
        return

    asyncpg = pytest.importorskip("asyncpg")
    dsn = os.environ.get("AMU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail("AMU_TEST_POSTGRES_DSN must identify a disposable test database")
    schema = "readiness_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    create_pool = asyncpg.create_pool

    async def private_pool(*args, **kwargs):
        settings = dict(kwargs.pop("server_settings", {}))
        settings["search_path"] = schema
        return await create_pool(*args, server_settings=settings, **kwargs)

    monkeypatch.setattr(asyncpg, "create_pool", private_pool)
    try:
        yield Config(database_url=dsn, database_ssl=False, **options)
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


async def rows(db, sql):
    async with db.execute(sql) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def table_names(db):
    if isinstance(db, PostgresDB):
        names = await rows(
            db,
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_schema=current_schema()",
        )
    else:
        names = await rows(db, "SELECT name FROM sqlite_master WHERE type='table'")
    return {row["name"] for row in names}


async def snapshot(db, tables):
    # Sorting representations gives deterministic comparison without assuming
    # any domain-specific key or changing timestamp/decimal driver values.
    result = {}
    for table in tables:
        result[table] = tuple(
            sorted(
                repr(sorted(row.items()))
                for row in await rows(db, f"SELECT * FROM {table}")
            )
        )
    return result


@asynccontextmanager
async def paper_owners(session, config, *, reconciliation=True, matching=False):
    paper = PaperStore(session.db)
    positions = None
    exits = None
    try:
        await paper.init_tables(initial_balance=config.paper_trading_initial_balance)
        await session.db.commit()
        for account in ("PAPER", "KALSHI_PAPER", "POLYMARKET_PAPER"):
            await paper.ensure_account(account, config.paper_trading_initial_balance)
        if reconciliation:
            positions = TrackedPositionStore(session.db)
            exits = ExitRuleStore(session.db)
            reconciler = PaperFillReconciler(
                paper,
                positions,
                OpportunityStore(session.db),
                ExitManager(store=exits),
                trade_store=TradeStore(session.db),
            )
            await reconciler.initialize()
        if matching:
            # Initialization only; no quotes, broker transport, or run loop.
            await PaperMatchingDriver(paper, {}, None).initialize()
        yield paper, positions
    finally:
        if exits is not None:
            await exits.close()
        if positions is not None:
            await positions.close()
        await paper.close()


async def test_session_requires_certification_and_becomes_unready_after_close(
    storage_config,
):
    session = StorageSession(storage_config)
    async with session:
        pending = await session.check()
        assert not pending.ready
        assert pending.phase == "pending"
        assert (await session.certify()).ready
        ready = await session.check()
        assert ready.ready
        assert ready.phase == "ready"
    closed = await session.check()
    assert not closed.ready
    assert closed.phase == "closed"


@pytest.mark.parametrize(
    "table",
    (
        "opportunities",
        "trade_executions",
        "risk_events",
        "tracked_positions",
        "position_exit_rules",
    ),
)
async def test_reachable_database_with_missing_required_table_is_unready(
    storage_config, table
):
    async with StorageSession(storage_config) as session:
        assert (await session.certify()).ready
        await session.db.execute(f"ALTER TABLE {table} RENAME TO readiness_hidden")
        await session.db.commit()
        assert await rows(session.db, "SELECT 1 AS reachable") == [{"reachable": 1}]
        broken = await session.check()
        assert not broken.ready
        assert broken.issues
        # Restore only the test-owned table. A readiness probe must not repair it.
        await session.db.execute(f"ALTER TABLE readiness_hidden RENAME TO {table}")
        await session.db.commit()
        assert (await session.check()).ready


async def test_missing_required_column_is_not_hidden_by_select_one(storage_config):
    async with StorageSession(storage_config) as session:
        assert (await session.certify()).ready
        await session.db.execute(
            "ALTER TABLE trade_executions RENAME COLUMN order_result TO readiness_hidden"
        )
        await session.db.commit()
        assert await rows(session.db, "SELECT 1 AS reachable") == [{"reachable": 1}]
        assert not (await session.check()).ready
        await session.db.execute(
            "ALTER TABLE trade_executions RENAME COLUMN readiness_hidden TO order_result"
        )
        await session.db.commit()
        assert (await session.check()).ready


async def test_certification_failure_carries_report(storage_config):
    async with StorageSession(storage_config) as session:
        await session.db.execute("ALTER TABLE opportunities RENAME TO readiness_hidden")
        await session.db.commit()
        with pytest.raises(StorageUnavailable) as failure:
            await session.certify()
        assert not failure.value.report.ready
        assert failure.value.report.issues


@pytest.mark.parametrize("matching", (False, True))
async def test_paper_profile_waits_for_selected_owners(storage_config, matching):
    config = storage_config.model_copy(
        update={"paper_trading": True, "paper_matching_enabled": matching}
    )
    async with StorageSession(config) as incomplete:
        with pytest.raises(StorageUnavailable):
            await incomplete.certify()
    async with StorageSession(config) as session:
        async with paper_owners(session, config, matching=matching) as (
            paper,
            positions,
        ):
            assert (
                await session.certify(paper_store=paper, position_store=positions)
            ).ready
            assert (await session.check()).ready
            if matching:
                await session.db.execute(
                    "ALTER TABLE paper_auto_ticks RENAME TO readiness_hidden"
                )
                await session.db.commit()
                assert not (await session.check()).ready
            else:
                # The matching table is neither provisioned nor needed.
                assert "paper_auto_ticks" not in await table_names(session.db)


async def test_paper_worker_needs_ledger_but_not_reconciliation_or_matching(
    storage_config,
):
    config = storage_config.model_copy(
        update={
            "paper_trading": True,
            "worker_mode": True,
            "paper_matching_enabled": True,
        }
    )
    async with StorageSession(config) as session:
        async with paper_owners(session, config, reconciliation=False) as (
            paper,
            positions,
        ):
            assert positions is None
            assert (await session.certify(paper_store=paper)).ready
            assert not {
                "paper_fill_jobs",
                "paper_auto_ticks",
                "tracked_fill_receipts",
            } & await table_names(session.db)
            assert (await session.check()).ready


async def test_paper_checks_preserve_cash_revisions_generations_and_rows(
    storage_config,
):
    config = storage_config.model_copy(
        update={"paper_trading": True, "paper_matching_enabled": True}
    )
    async with StorageSession(config) as session:
        async with paper_owners(session, config, matching=True) as (paper, positions):
            opportunities = OpportunityStore(session.db)
            opportunity = Opportunity(
                id="readiness-preserved",
                agent_name="readiness-test",
                symbol=Symbol("AAPL"),
                signal="hold",
                confidence=0.5,
                reasoning="persistent evidence",
                data={},
                timestamp=datetime.now(timezone.utc),
            )
            assert await opportunities.save(opportunity)
            saved = await opportunities.load(opportunity.id)
            revision = saved.data[REVISION_KEY]
            generations = {
                account: await paper.account_generation(account)
                for account in ("PAPER", "KALSHI_PAPER", "POLYMARKET_PAPER")
            }
            assert all(generations.values())
            accounts = await rows(
                session.db, "SELECT account_id, cash FROM paper_accounts"
            )
            assert {row["account_id"] for row in accounts} == set(generations)
            assert all(
                row["cash"] == config.paper_trading_initial_balance for row in accounts
            )
            tables = (
                "opportunities",
                "trade_executions",
                "risk_events",
                "tracked_positions",
                "position_exit_rules",
                "paper_accounts",
                "paper_positions",
                "paper_orders",
                "paper_order_terms",
                "paper_fill_events",
                "paper_match_ticks",
                "paper_dispatches",
                "paper_risk_coverage",
                "paper_risk_events",
                "paper_fill_jobs",
                "tracked_fill_receipts",
                "paper_auto_ticks",
            )
            before = await snapshot(session.db, tables)
            assert (
                await session.certify(paper_store=paper, position_store=positions)
            ).ready
            for _ in range(3):
                assert (await session.check()).ready
            assert await snapshot(session.db, tables) == before
            assert (await opportunities.load(opportunity.id)).data[
                REVISION_KEY
            ] == revision
            assert {
                account: await paper.account_generation(account)
                for account in generations
            } == generations


async def test_reopening_owners_preserves_existing_account_and_opportunity_identity(
    storage_config,
):
    config = storage_config.model_copy(update={"paper_trading": True})
    tables = (
        "paper_accounts",
        "paper_risk_coverage",
        "opportunities",
        "paper_dispatches",
    )
    async with StorageSession(config) as first:
        async with paper_owners(first, config) as (paper, positions):
            await OpportunityStore(first.db).save(
                Opportunity(
                    id="existing-offer",
                    agent_name="readiness-test",
                    symbol=Symbol("AAPL"),
                    signal="hold",
                    confidence=0.5,
                    reasoning="existing saved revision",
                    data={},
                    timestamp=datetime.now(timezone.utc),
                )
            )
            # Fixture evidence only: no dispatch, order admission or execution.
            async with paper.transaction() as ledger:
                await ledger.execute(
                    "UPDATE paper_accounts SET cash=4321, buying_power=4321, "
                    "net_liquidation=4321 WHERE account_id='PAPER'"
                )
                await paper.insert_dispatch(
                    "preserved-dispatch",
                    "PAPER",
                    "{}",
                    await paper.account_generation("PAPER"),
                    "{}",
                )
            assert (
                await first.certify(paper_store=paper, position_store=positions)
            ).ready
            before = await snapshot(first.db, tables)
    changed = config.model_copy(update={"paper_trading_initial_balance": 99999.0})
    async with StorageSession(changed) as reopened:
        async with paper_owners(reopened, changed) as (paper, positions):
            assert (
                await reopened.certify(paper_store=paper, position_store=positions)
            ).ready
            assert await snapshot(reopened.db, tables) == before
