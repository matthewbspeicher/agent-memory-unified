import pytest
from decimal import Decimal
import uuid

from execution.arbitrage import (
    ArbCoordinator,
    ArbTrade,
    ArbLeg,
    ArbState,
    SequencingStrategy,
)
from broker.models import Symbol, AssetType, LimitOrder, OrderSide, TIF, Quote
from execution.service import ExecutionService
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.rules import MaxPositionSize, MaxDailyLoss, MaxDailyTrades
from adapters.kalshi.paper import KalshiPaperBroker, KALSHI_PAPER_ACCOUNT_ID
from adapters.polymarket.paper import PolymarketPaperBroker, POLYMARKET_PAPER_ACCOUNT_ID
from storage.paper import PaperStore
from storage.arbitrage import ArbStore
import aiosqlite
from config import Config


from tests.execution_controls import AdmissionLuaDouble


class InMemoryControlStore(AdmissionLuaDouble):
    """Redis semantics needed by admission, retained across both leg requests."""

    def __init__(self, halted=False):
        self.data = {"kill_switch:active": "true" if halted else "false"}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def delete(self, key):
        self.data.pop(key, None)


class DeterministicQuotes:
    async def get_quote(self, symbol):
        # Executable limit prices, with fresh timestamps on every observation.
        if symbol.ticker == "TEST-YES":
            return Quote(
                symbol, bid=Decimal("0.43"), ask=Decimal("0.44"), last=Decimal("0.44")
            )
        if symbol.ticker == "0x123":
            return Quote(
                symbol, bid=Decimal("0.56"), ask=Decimal("0.57"), last=Decimal("0.56")
            )
        raise ValueError(f"Unexpected test symbol {symbol}")


@pytest.fixture
async def paper_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    store = PaperStore(db)
    await store.init_tables()
    yield store
    await db.close()


@pytest.fixture
async def arb_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS arb_trades (
            id TEXT PRIMARY KEY,
            symbol_a TEXT NOT NULL,
            symbol_b TEXT NOT NULL,
            state TEXT NOT NULL,
            sequencing TEXT NOT NULL,
            expected_profit_bps INTEGER NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS arb_legs (
            trade_id TEXT NOT NULL,
            leg_name TEXT NOT NULL,
            broker_id TEXT NOT NULL,
            order_data TEXT NOT NULL,
            fill_price TEXT,
            fill_quantity TEXT NOT NULL,
            status TEXT NOT NULL,
            external_order_id TEXT,
            PRIMARY KEY (trade_id, leg_name)
        )
    """)
    await db.commit()
    store = ArbStore(db)
    yield store
    await db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("halted", [False, True])
async def test_arbitrage_e2e_dual_paper(paper_store, arb_store, halted):
    # Fresh temporary accounts provide reconciled daily metrics from the real
    # paper ledger. Only prices and the persistent-control transport are fakes.
    for account in (KALSHI_PAPER_ACCOUNT_ID, POLYMARKET_PAPER_ACCOUNT_ID):
        await paper_store.ensure_account(account, Decimal("10000"))
    quotes = DeterministicQuotes()
    kalshi_broker = KalshiPaperBroker(store=paper_store, market_data=quotes)
    await kalshi_broker.connection.connect()

    poly_broker = PolymarketPaperBroker(store=paper_store, market_data=quotes)
    await poly_broker.connection.connect()

    settings = Config()

    brokers = {"kalshi_paper": kalshi_broker, "polymarket_paper": poly_broker}
    control = InMemoryControlStore(halted)
    risk = RiskEngine(
        [MaxPositionSize(100, 100), MaxDailyLoss(100), MaxDailyTrades(10)],
        KillSwitch(),
    )
    execution = ExecutionService(risk, control)
    execution.register_brokers(brokers)
    coordinator = ArbCoordinator(
        brokers=brokers,
        store=arb_store,
        config=settings,
        execution_service=execution,
    )

    sym_a = Symbol(ticker="TEST-YES", asset_type=AssetType.PREDICTION)
    sym_b = Symbol(ticker="0x123", asset_type=AssetType.PREDICTION)

    order_a = LimitOrder(
        symbol=sym_a,
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        limit_price=Decimal("0.45"),
        account_id=KALSHI_PAPER_ACCOUNT_ID,
        time_in_force=TIF.GTC,
    )

    order_b = LimitOrder(
        symbol=sym_b,
        side=OrderSide.SELL,
        quantity=Decimal("10"),
        limit_price=Decimal("0.55"),
        account_id=POLYMARKET_PAPER_ACCOUNT_ID,
        time_in_force=TIF.GTC,
    )

    leg_a = ArbLeg(broker_id="kalshi_paper", order=order_a)
    leg_b = ArbLeg(broker_id="polymarket_paper", order=order_b)

    trade = ArbTrade(
        id=str(uuid.uuid4()),
        symbol_a=sym_a.ticker,
        symbol_b=sym_b.ticker,
        leg_a=leg_a,
        leg_b=leg_b,
        sequencing=SequencingStrategy.KALSHI_FIRST,
        expected_profit_bps=1000,
    )

    # Execute the arb
    success = await coordinator.execute_arbitrage(trade)
    if halted:
        assert success is False
        assert trade.state == ArbState.FAILED
        for account in (KALSHI_PAPER_ACCOUNT_ID, POLYMARKET_PAPER_ACCOUNT_ID):
            assert await paper_store.get_order_history(account) == []
            assert await paper_store.get_positions(account) == []
            assert (await paper_store.get_balance(account)).cash == Decimal("10000")
    else:
        assert success is True
        assert trade.state == ArbState.COMPLETED
        assert trade.leg_a.status == "filled"
        assert trade.leg_b.status == "filled"
        assert trade.leg_a.fill_quantity == trade.leg_b.fill_quantity == Decimal("10")
        for broker, account, expected_qty in (
            (kalshi_broker, KALSHI_PAPER_ACCOUNT_ID, Decimal("10")),
            (poly_broker, POLYMARKET_PAPER_ACCOUNT_ID, Decimal("-10")),
        ):
            history = await paper_store.get_order_history(account)
            assert len(history) == 1
            assert history[0].filled_quantity == Decimal("10")
            assert (await paper_store.get_positions(account))[
                0
            ].quantity == expected_qty
            state = await broker.account.get_risk_state(account)
            assert state.complete is True
            assert state.context.daily_trade_count == 1
            assert state.context.daily_pnl is not None
        diagnostics = await execution.reconciliation_status()
        assert len(diagnostics["reservations"]) == 2
        assert diagnostics["attempt"]["status"] == "acknowledged"
    assert await control.get("execution:admission:lock") is None
