"""Configured paper funding against an empty disposable PostgreSQL schema."""

import os
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest

from api.startup.brokers import setup_brokers
from broker.paper import PaperBroker
from config import BrokerConfig, Config
from storage.paper import PaperStore
from storage.postgres import PostgresDB

pytestmark = pytest.mark.integration
ACCOUNTS = ("PAPER", "KALSHI_PAPER", "POLYMARKET_PAPER")


@pytest.fixture
async def empty_database():
    dsn = os.environ.get("AMU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail("AMU_TEST_POSTGRES_DSN must identify a disposable test database")
    schema = "starting_balance_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    pool = await asyncpg.create_pool(
        dsn, min_size=2, max_size=4, server_settings={"search_path": schema}
    )
    try:
        yield PostgresDB(pool)
    finally:
        await pool.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


def paper_config(balance):
    # Config is constructed directly; no environment file or live adapter is used.
    return Config(
        paper_trading=True,
        paper_trading_initial_balance=balance,
        worker_mode=True,
        broker=BrokerConfig(ib_host=""),
    )


@pytest.mark.parametrize("balance", [0, 25000.25])
@pytest.mark.parametrize("provided_broker", [False, True])
async def test_fresh_accounts_and_restart_preserve_configured_funding(
    empty_database, balance, provided_broker
):
    supplied = PaperBroker(PaperStore(empty_database)) if provided_broker else None
    _, _, store = await setup_brokers(paper_config(balance), empty_database, supplied)
    generations = {}
    try:
        for account in ACCOUNTS:
            snapshot = await store.get_risk_state(account, None)
            expected = Decimal(str(balance))
            assert snapshot.complete and snapshot.epoch
            assert snapshot.context.daily_pnl == 0
            assert snapshot.context.daily_trade_count == 0
            funds = snapshot.context.balance
            assert (funds.cash, funds.net_liquidation, funds.buying_power) == (
                expected,
            ) * 3
            assert funds.maintenance_margin == 0
            generations[account] = snapshot.epoch
    finally:
        await store.close()
        if supplied is not None:
            await supplied.orders.store.close()

    _, _, restarted = await setup_brokers(paper_config(75000), empty_database, None)
    try:
        for account in ACCOUNTS:
            assert (await restarted.get_balance(account)).cash == Decimal(str(balance))
            assert await restarted.account_generation(account) == generations[account]
    finally:
        await restarted.close()


async def test_restart_preserves_balances_until_an_explicit_paper_reset(empty_database):
    settings = paper_config(25000)
    settings.worker_mode = False
    broker, _, store = await setup_brokers(settings, empty_database, None)
    generation = await store.account_generation("PAPER")
    try:
        async with store.transaction() as db:
            await db.execute(
                "UPDATE paper_accounts SET cash=12345, net_liquidation=12500, buying_power=1000, maintenance_margin=50 WHERE account_id='PAPER'"
            )
    finally:
        await store.close()

    settings.paper_trading_initial_balance = 75000
    broker, _, restarted = await setup_brokers(settings, empty_database, None)
    try:
        funds = await restarted.get_balance("PAPER")
        assert (
            funds.cash,
            funds.net_liquidation,
            funds.buying_power,
            funds.maintenance_margin,
        ) == (12345, 12500, 1000, 50)
        assert await restarted.account_generation("PAPER") == generation
        await broker.reset()
        assert (await restarted.get_balance("PAPER")).cash == 75000
        assert await restarted.account_generation("PAPER") != generation
        for account in ACCOUNTS[1:]:
            assert (await restarted.get_balance(account)).cash == 25000
    finally:
        await restarted.close()
