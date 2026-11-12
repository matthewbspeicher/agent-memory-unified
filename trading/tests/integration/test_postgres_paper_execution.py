"""Opt-in PostgreSQL qualification. Use a disposable database, never an app DSN."""

import asyncio
import os
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from broker.models import MarketOrder, OrderSide, Quote, Symbol, FeeModel, OrderStatus
from broker.paper import PaperBroker
from execution.service import ExecutionService, ExecutionRejected
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.rules import MaxPositionSize, MaxDailyLoss, MaxDailyTrades
from storage.paper import PaperStore
from storage.postgres import PostgresDB

pytestmark = pytest.mark.integration


@pytest.fixture
async def ledger():
    dsn = os.environ.get("AMU_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail("AMU_TEST_POSTGRES_DSN must identify a disposable test database")
    schema = "paper_test_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    pool = await asyncpg.create_pool(
        dsn, min_size=2, max_size=5, server_settings={"search_path": schema}
    )
    db = PostgresDB(pool)
    store = PaperStore(db)
    try:
        from storage.db import init_db_postgres

        await init_db_postgres(db)
        await store.init_tables()
        yield store, db, pool
    finally:
        await store.close()
        await pool.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


from tests.execution_controls import AdmissionLuaDouble


class Controls(AdmissionLuaDouble):
    def __init__(self):
        self.data = {"kill_switch:active": "false"}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def delete(self, key):
        self.data.pop(key, None)


def rig(store, controls=None, max_trades=5, fee_model=None):
    symbol = Symbol("TEST")
    quotes = SimpleNamespace(
        get_quote=AsyncMock(
            side_effect=lambda s: Quote(s, bid=D(100), ask=D(100), last=D(100))
        )
    )
    broker = PaperBroker(store, market_data=quotes, max_slippage=0, fee_model=fee_model)
    risk = RiskEngine(
        [MaxPositionSize(10000, 100), MaxDailyLoss(1000), MaxDailyTrades(max_trades)],
        KillSwitch(),
    )
    service = ExecutionService(risk, controls or Controls())
    service.register_brokers({"paper": broker})
    order = MarketOrder(symbol, OrderSide.BUY, D(2), "PAPER")
    return broker, service, order, quotes


async def test_shared_boundary_metrics_restart_halt_and_limits(ledger):
    store, db, _ = ledger
    controls = Controls()
    broker, service, order, quotes = rig(store, controls, max_trades=1)
    result = await service.submit(broker, "PAPER", order)
    assert result.status == OrderStatus.FILLED
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_trade_count == 1
    assert state.context.balance.cash == 99800
    assert state.context.balance.net_liquidation == 100000
    assert state.context.positions[0].quantity == 2
    restarted = PaperStore(db)
    await restarted.init_tables()
    broker2, service2, order2, _ = rig(restarted, controls, max_trades=1)
    assert (await broker2.account.get_risk_state("PAPER")).epoch == state.epoch
    with pytest.raises(ExecutionRejected):
        await service2.submit(broker2, "PAPER", order2)
    controls.data["kill_switch:active"] = "true"
    with pytest.raises(ExecutionRejected):
        await service.submit(broker, "PAPER", order)
    assert (await store.get_balance("PAPER")).cash == 99800
    await restarted.close()


async def test_write_failure_rolls_back_entire_fill(ledger):
    store, db, _ = ledger
    broker, service, order, _ = rig(store)
    store.save_order = AsyncMock(side_effect=RuntimeError("failure after fill"))
    with pytest.raises(ExecutionRejected, match="unknown"):
        await service.submit(broker, "PAPER", order)
    assert (await store.get_balance("PAPER")).cash == 100000
    assert await store.get_positions("PAPER") == []
    assert await store.get_order_history("PAPER") == []
    assert await db.fetchall("SELECT * FROM paper_risk_events") == []


async def test_transaction_isolation_rollback_cancellation_and_root_commit(ledger):
    store, db, pool = ledger
    entered = asyncio.Event()

    async def write():
        async with store.transaction() as tx:
            await tx.execute(
                "UPDATE paper_accounts SET cash=1 WHERE account_id='PAPER'"
            )
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(write())
    await entered.wait()
    await db.commit()  # unrelated facade cannot commit the owned transaction
    assert (
        await db.fetchone("SELECT cash FROM paper_accounts WHERE account_id='PAPER'")
    )["cash"] == 100000
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await store.get_balance("PAPER")).cash == 100000
    async with pool.acquire() as conn:
        assert not conn.is_in_transaction()


async def test_independent_stores_serialize_writes_and_snapshots(ledger):
    store, db, _ = ledger
    second = PaperStore(db)
    entered, release = asyncio.Event(), asyncio.Event()

    async def write():
        async with store.transaction() as tx:
            await tx.execute(
                "UPDATE paper_accounts SET cash=cash-10 WHERE account_id='PAPER'"
            )
            entered.set()
            await release.wait()

    task = asyncio.create_task(write())
    await entered.wait()
    snapshot = asyncio.create_task(second.get_risk_state("PAPER", None))
    await asyncio.sleep(0.05)
    assert not snapshot.done()
    release.set()
    await task
    assert (await snapshot).context.balance.cash == 99990
    await second.close()


async def test_concurrent_store_fills_do_not_lose_position_updates(ledger):
    store, db, _ = ledger
    other = PaperStore(db)
    one, _, order, _ = rig(store)
    two, _, _, _ = rig(other)
    # Deliberately exercise ledger serialization without the Redis admission lock.
    results = await asyncio.gather(
        one.orders.place_order("PAPER", order), two.orders.place_order("PAPER", order)
    )
    assert all(r.status == OrderStatus.FILLED for r in results)
    state = await one.account.get_risk_state("PAPER")
    assert state.context.daily_trade_count == 2
    assert state.context.positions[0].quantity == 4
    assert state.context.balance.cash == 99600
    await other.close()


async def test_startup_preserves_accounts_and_initializes_predictions(ledger):
    from api.startup.brokers import setup_brokers
    from config import Config, BrokerConfig

    store, db, _ = ledger
    generation = await store.account_generation("PAPER")
    await db.execute(
        "UPDATE paper_accounts SET cash=12345, net_liquidation=12500, buying_power=1000, maintenance_margin=50 WHERE account_id='PAPER'"
    )
    config = Config(
        paper_trading=True,
        paper_trading_initial_balance=25000.25,
        worker_mode=True,
        broker=BrokerConfig(ib_host=""),
    )
    _, _, initialized = await setup_brokers(config, db, None)
    funds = await initialized.get_balance("PAPER")
    assert (funds.cash, funds.net_liquidation, funds.buying_power, funds.maintenance_margin) == (12345, 12500, 1000, 50)
    assert await initialized.account_generation("PAPER") == generation
    for account in ("KALSHI_PAPER", "POLYMARKET_PAPER"):
        state = await initialized.get_risk_state(account, None)
        assert state.complete and state.epoch
        assert state.context.daily_trade_count == 0
        assert state.context.balance.cash == D("25000.25")
    await initialized.close()


async def test_legacy_missing_coverage_is_not_invented(ledger):
    store, db, _ = ledger
    await db.execute("DELETE FROM paper_risk_coverage")
    await store.init_tables()
    with pytest.raises(ValueError, match="coverage is incomplete"):
        await store.get_risk_state("PAPER", None)


async def test_fees_loss_marks_and_reset_epoch(ledger):
    store, db, _ = ledger

    class Fee(FeeModel):
        def calculate(self, order, fill_price):
            return D(2)

    broker, service, order, quotes = rig(store, fee_model=Fee())
    await service.submit(broker, "PAPER", order)
    quotes.get_quote.side_effect = lambda s: Quote(s, bid=D(90), ask=D(90), last=D(90))
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_pnl == -22
    assert state.context.balance.net_liquidation == 99978
    await broker.reset()
    reset = await broker.account.get_risk_state("PAPER")
    assert reset.epoch != state.epoch
    assert reset.context.daily_trade_count == 0
    assert reset.context.daily_pnl == 0


async def test_normal_schema_initialization_and_database_close(ledger):
    from storage.db import init_db_postgres, DatabaseConnection
    from config import Config

    store, db, pool = ledger
    await init_db_postgres(db)
    await store.init_tables()
    assert (await store.get_risk_state("PAPER", None)).complete
    # The manager must recognize a pooled backend and close the pool.
    manager = DatabaseConnection(Config())
    manager.connection = db
    assert manager.connection.pool is pool


async def test_resolution_and_carry_accounting(ledger):
    from broker.models import AssetType

    store, db, _ = ledger
    broker, service, order, quotes = rig(store)
    await service.submit(broker, "PAPER", order)
    positions = await store.get_positions("PAPER")
    assert await broker.account.apply_carry_fees(positions, D("0.01")) == 2
    assert (await broker.account.get_risk_state("PAPER")).context.daily_pnl == -2
    # Settlement and its risk event must share the same transaction, too.
    symbol = Symbol("PRED", AssetType.PREDICTION)
    async with store.transaction():
        await store.record_fill(
            "PAPER", symbol, OrderSide.BUY, D(2), D("0.5"), order_id="pred"
        )
        await store.save_order(
            "pred",
            "PAPER",
            symbol,
            OrderSide.BUY,
            D(2),
            OrderStatus.FILLED.value,
            D(2),
            D("0.5"),
        )
    await store.record_binary_resolution("PAPER", symbol, D(2), D("0.5"), "YES")
    await store.record_binary_resolution("PAPER", symbol, D(2), D("0.5"), "YES")
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_pnl == -1
    events = await db.fetchall(
        "SELECT * FROM paper_risk_events WHERE kind='resolution'"
    )
    assert len(events) == 1


@pytest.mark.parametrize(
    "venue,account", [("kalshi", "KALSHI_PAPER"), ("polymarket", "POLYMARKET_PAPER")]
)
async def test_prediction_paper_uses_same_boundary(ledger, venue, account):
    from broker.models import AssetType, LimitOrder
    from adapters.kalshi.paper import KalshiPaperBroker
    from adapters.polymarket.paper import PolymarketPaperBroker

    store, db, _ = ledger
    await store.ensure_account(account, 10000)
    symbol = Symbol("PRED", AssetType.PREDICTION)
    quotes = SimpleNamespace(
        get_quote=AsyncMock(
            side_effect=lambda s: Quote(s, bid=D("0.5"), ask=D("0.5"), last=D("0.5"))
        )
    )
    factory = KalshiPaperBroker if venue == "kalshi" else PolymarketPaperBroker
    broker = factory(store, market_data=quotes)
    _, service, _, _ = rig(store)
    service.register_brokers({venue: broker})
    result = await service.submit(
        broker,
        account,
        LimitOrder(symbol, OrderSide.BUY, D(2), account, limit_price=D("0.5")),
    )
    assert result.status == OrderStatus.FILLED
    snapshot = await broker.account.get_risk_state(account)
    assert snapshot.context.daily_trade_count == 1
    assert snapshot.context.positions[0].quantity == 2
