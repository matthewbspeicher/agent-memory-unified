"""Paper startup remains readable on unsupported storage, without execution admission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from decimal import Decimal

import aiosqlite
import pytest

from api.startup.brokers import setup_brokers
from config import Config, BrokerConfig
from broker.paper import PaperBroker
from storage.paper import PaperStore


def config(balance=10000):
    return Config(
        paper_trading=True,
        paper_trading_initial_balance=balance,
        worker_mode=True,
        broker=BrokerConfig(ib_host=""),
    )


async def test_unsupported_paper_backend_keeps_startup_but_denies_risk_context(
    monkeypatch, caplog
):
    import storage.paper

    database = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    store = PaperStore(database)
    store.init_tables = AsyncMock()
    store.ensure_account = AsyncMock(
        side_effect=AssertionError("unsupported account initialization")
    )
    monkeypatch.setattr(storage.paper, "PaperStore", lambda db: store)
    primary, brokers, result_store = await setup_brokers(config(), database, None)
    assert primary is None and brokers == {} and result_store is store
    store.ensure_account.assert_not_awaited()
    assert "Paper execution unavailable" in caplog.text
    with pytest.raises(ValueError, match="supported transactional"):
        await store.get_risk_state("PAPER", None)
    await store.close()


async def test_new_sqlite_primary_and_prediction_accounts_have_coverage(tmp_path):
    async with aiosqlite.connect(tmp_path / "startup.db") as database:
        database.row_factory = aiosqlite.Row
        _, _, store = await setup_brokers(config(), database, None)
        try:
            assert await store._get_db() is not database
            for account in ("PAPER", "KALSHI_PAPER", "POLYMARKET_PAPER"):
                snapshot = await store.get_risk_state(account, None)
                assert snapshot.complete
                assert snapshot.epoch
                assert snapshot.context.daily_pnl == 0
                assert snapshot.context.daily_trade_count == 0
                assert (
                    snapshot.context.balance.cash
                    == config().paper_trading_initial_balance
                )
        finally:
            await store.close()


@pytest.mark.parametrize("in_memory", [False, True])
@pytest.mark.parametrize("provided_broker", [False, True])
async def test_fresh_startup_uses_configured_balance(
    tmp_path, in_memory, provided_broker
):
    path = ":memory:" if in_memory else tmp_path / "configured.db"
    async with aiosqlite.connect(path) as database:
        database.row_factory = aiosqlite.Row
        supplied = PaperBroker(PaperStore(database)) if provided_broker else None
        store = None
        try:
            _, _, store = await setup_brokers(config(25000.25), database, supplied)
            for account in ("PAPER", "KALSHI_PAPER", "POLYMARKET_PAPER"):
                balance = await store.get_balance(account)
                assert (
                    balance.cash,
                    balance.net_liquidation,
                    balance.buying_power,
                ) == (Decimal("25000.25"),) * 3
                assert balance.maintenance_margin == 0
                snapshot = await store.get_risk_state(account, None)
                assert snapshot.complete and snapshot.epoch
                assert snapshot.context.daily_trade_count == 0
        finally:
            if store is not None:
                await store.close()
            if supplied is not None:
                await supplied.orders.store.close()


@pytest.mark.parametrize("in_memory", [False, True])
async def test_changed_config_preserves_all_existing_balances_and_coverage(
    tmp_path, in_memory
):
    path = ":memory:" if in_memory else tmp_path / "preserved.db"
    async with aiosqlite.connect(path) as database:
        database.row_factory = aiosqlite.Row
        _, _, store = await setup_brokers(config(25000), database, None)
        try:
            async with store.transaction() as db:
                for index, account in enumerate(
                    ("PAPER", "KALSHI_PAPER", "POLYMARKET_PAPER")
                ):
                    await db.execute(
                        "UPDATE paper_accounts SET cash=?, net_liquidation=?, buying_power=?, maintenance_margin=? WHERE account_id=?",
                        (
                            12345 + index,
                            12500 + index,
                            1000 + index,
                            50 + index,
                            account,
                        ),
                    )
            db = await store._get_db()
            accounts_before = [
                tuple(row)
                for row in await (
                    await db.execute("SELECT * FROM paper_accounts ORDER BY account_id")
                ).fetchall()
            ]
            coverage_before = [
                tuple(row)
                for row in await (
                    await db.execute(
                        "SELECT * FROM paper_risk_coverage ORDER BY account_id"
                    )
                ).fetchall()
            ]
        finally:
            await store.close()
        _, _, restarted = await setup_brokers(config(75000), database, None)
        try:
            db = await restarted._get_db()
            assert [
                tuple(row)
                for row in await (
                    await db.execute("SELECT * FROM paper_accounts ORDER BY account_id")
                ).fetchall()
            ] == accounts_before
            assert [
                tuple(row)
                for row in await (
                    await db.execute(
                        "SELECT * FROM paper_risk_coverage ORDER BY account_id"
                    )
                ).fetchall()
            ] == coverage_before
        finally:
            await restarted.close()
