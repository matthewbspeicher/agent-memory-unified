"""Real temporary paper ledger checks, with deterministic mocked quotes only."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from broker.models import (
    MarketOrder,
    LimitOrder,
    OrderSide,
    Quote,
    Symbol,
    AssetType,
    FeeModel,
)
from broker.paper import PaperBroker
from storage.paper import PaperStore

D = Decimal


@pytest.fixture
async def ledger(tmp_path):
    async with aiosqlite.connect(tmp_path / "paper.db") as db:
        db.row_factory = aiosqlite.Row
        store = PaperStore(db)
        await store.init_tables()
        try:
            yield store, await store._get_db()
        finally:
            await store.close()


def make_broker(store, price="100", fee_model=None):
    symbol = Symbol("TEST")
    quotes = SimpleNamespace(
        get_quote=AsyncMock(
            return_value=Quote(
                symbol,
                bid=D(price),
                ask=D(price),
                last=D(price),
                timestamp=datetime.now(timezone.utc),
            )
        ),
        get_order_book=AsyncMock(return_value={}),
    )
    return (
        PaperBroker(store, market_data=quotes, max_slippage=0, fee_model=fee_model),
        quotes,
        symbol,
    )


async def submit(broker, symbol, side, quantity="2"):
    return await broker.orders.place_order(
        "PAPER", MarketOrder(symbol, side, D(quantity), "PAPER")
    )


async def test_daily_pnl_count_marks_and_restart(ledger):
    store, db = ledger
    broker, quotes, symbol = make_broker(store)
    empty = await broker.account.get_risk_state("PAPER")
    assert empty.context.daily_pnl == 0
    assert empty.context.daily_trade_count == 0
    buy = await submit(broker, symbol, OrderSide.BUY)
    assert (
        await broker.account.get_risk_state("PAPER")
    ).context.balance.net_liquidation == 100000
    quotes.get_quote.return_value = Quote(
        symbol,
        bid=D("90"),
        ask=D("90"),
        last=D("90"),
        timestamp=datetime.now(timezone.utc),
    )
    marked = await broker.account.get_risk_state("PAPER")
    assert marked.context.daily_pnl == -20
    assert marked.context.balance.net_liquidation == 99980
    sell = await submit(broker, symbol, OrderSide.SELL)
    restarted = PaperStore(db)
    await restarted.init_tables()
    snapshot = await restarted.get_risk_state("PAPER", quotes)
    await restarted.close()
    assert snapshot.context.positions == []
    assert snapshot.context.daily_pnl == -20
    assert snapshot.context.daily_trade_count == 2
    assert {buy.order_id, sell.order_id} <= snapshot.terminal_order_ids


async def test_commissions_and_carry_are_daily_losses(ledger):
    class FixedFee(FeeModel):
        def calculate(self, order, fill_price):
            return D("2")

    store, db = ledger
    broker, quotes, symbol = make_broker(store, fee_model=FixedFee())
    await submit(broker, symbol, OrderSide.BUY)
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_pnl == -2
    await broker.account.apply_carry_fees(state.context.positions, daily_rate=D("0.01"))
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_pnl == -4
    assert state.context.balance.net_liquidation == 99996


async def test_legacy_current_day_fill_cannot_be_assumed_complete(ledger):
    store, db = ledger
    await db.execute(
        "INSERT INTO paper_orders (order_id, account_id, symbol, side, quantity, status, filled_quantity, avg_fill_price) VALUES ('legacy','PAPER','TEST','BUY',1,'FILLED',1,100)"
    )
    await db.commit()
    with pytest.raises(ValueError, match="evidence is incomplete"):
        await store.get_risk_state("PAPER", None)


async def test_legacy_migration_blocks_day_and_preserves_rows(ledger):
    store, db = ledger
    await db.execute("DELETE FROM paper_risk_coverage")
    await db.commit()
    await store.init_tables()
    with pytest.raises(ValueError, match="coverage is incomplete"):
        await store.get_risk_state("PAPER", None)
    assert (await store.get_balance("PAPER")).cash == 100000
    tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    row = await (
        await db.execute(
            "SELECT complete_from FROM paper_risk_coverage WHERE account_id='PAPER'"
        )
    ).fetchone()
    assert row["complete_from"] == tomorrow


async def test_legacy_previous_day_fills_do_not_invent_today_losses(ledger):
    store, db = ledger
    await db.execute(
        "INSERT INTO paper_orders (order_id, account_id, symbol, side, quantity, status, filled_quantity, avg_fill_price, created_at) VALUES ('old','PAPER','TEST','BUY',1,'FILLED',1,100,'2000-01-01 00:00:00')"
    )
    await db.commit()
    state = await store.get_risk_state("PAPER", None)
    assert state.context.daily_trade_count == 0
    assert state.context.daily_pnl == 0


async def test_failed_order_write_rolls_back_fill_and_risk_evidence(
    ledger, monkeypatch
):
    store, db = ledger
    broker, quotes, symbol = make_broker(store)
    monkeypatch.setattr(
        store, "save_order", AsyncMock(side_effect=RuntimeError("disk failure"))
    )
    with pytest.raises(RuntimeError, match="disk failure"):
        await submit(broker, symbol, OrderSide.BUY)
    assert (await store.get_balance("PAPER")).cash == 100000
    assert await store.get_positions("PAPER") == []
    assert (await broker.account.get_risk_state("PAPER")).context.daily_trade_count == 0


async def test_stale_position_quotes_block_context(ledger):
    store, _ = ledger
    broker, quotes, symbol = make_broker(store)
    await submit(broker, symbol, OrderSide.BUY)
    quotes.get_quote.return_value = Quote(
        symbol,
        last=D("100"),
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    with pytest.raises(ValueError, match="stale"):
        await broker.account.get_risk_state("PAPER")


async def test_reset_clears_risk_ledger_with_orders(ledger):
    store, db = ledger
    broker, quotes, symbol = make_broker(store)
    await submit(broker, symbol, OrderSide.BUY)
    await broker.reset()
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_trade_count == 0
    assert state.context.positions == []
    assert state.context.daily_pnl == 0


@pytest.mark.parametrize("venue", ["kalshi", "polymarket"])
async def test_prediction_fill_commits_cash_order_and_risk_event(ledger, venue):
    from adapters.kalshi.paper import KalshiPaperBroker
    from adapters.polymarket.paper import PolymarketPaperBroker

    store, db = ledger
    cls = KalshiPaperBroker if venue == "kalshi" else PolymarketPaperBroker
    symbol = Symbol("CONTRACT", AssetType.PREDICTION)
    quotes = SimpleNamespace(
        get_quote=AsyncMock(
            return_value=Quote(
                symbol,
                bid=D("0.5"),
                ask=D("0.5"),
                last=D("0.5"),
                timestamp=datetime.now(timezone.utc),
            )
        )
    )
    broker = cls(store, slippage_cents=0, market_data=quotes)
    account = broker.orders.paper_account_id
    await store.ensure_account(account, 100000)
    order = LimitOrder(symbol, OrderSide.BUY, D("2"), account, limit_price=D("0.5"))
    result = await broker.orders.place_order(account, order)
    assert not db.in_transaction
    state = await broker.account.get_risk_state(account)
    assert result.order_id in state.terminal_order_ids
    assert state.context.daily_trade_count == 1
    assert state.context.balance.net_liquidation == 100000


async def test_resolution_loss_is_in_daily_risk(ledger):
    store, db = ledger
    from adapters.kalshi.paper import KalshiPaperBroker

    symbol = Symbol("CONTRACT", AssetType.PREDICTION)
    quotes = SimpleNamespace(
        get_quote=AsyncMock(
            return_value=Quote(
                symbol, last=D("0.5"), timestamp=datetime.now(timezone.utc)
            )
        )
    )
    broker = KalshiPaperBroker(store, slippage_cents=0, market_data=quotes)
    account = broker.orders.paper_account_id
    await store.ensure_account(account, 100000)
    await broker.orders.place_order(
        account,
        LimitOrder(symbol, OrderSide.BUY, D("2"), account, limit_price=D("0.5")),
    )
    await store.record_binary_resolution(account, symbol, D("2"), D("0.5"), "NO")
    state = await broker.account.get_risk_state(account)
    assert state.context.daily_pnl == -1
    assert state.context.daily_trade_count == 1


async def test_cancelled_order_write_rolls_back_fill(ledger, monkeypatch):
    import asyncio

    store, db = ledger
    broker, quotes, symbol = make_broker(store)
    monkeypatch.setattr(
        store, "save_order", AsyncMock(side_effect=asyncio.CancelledError())
    )
    with pytest.raises(asyncio.CancelledError):
        await submit(broker, symbol, OrderSide.BUY)
    assert not db.in_transaction
    assert (await store.get_balance("PAPER")).cash == 100000
    assert (await broker.account.get_risk_state("PAPER")).context.daily_trade_count == 0


async def test_context_rejects_account_change_while_loading_quotes(ledger):
    store, db = ledger
    broker, quotes, symbol = make_broker(store)
    await submit(broker, symbol, OrderSide.BUY)

    async def changing_quote(symbol):
        await db.execute(
            "UPDATE paper_accounts SET cash=cash-1 WHERE account_id='PAPER'"
        )
        await store.record_risk_event("PAPER", "carry_fee", D("-1"))
        await db.commit()
        return Quote(symbol, last=D("100"), timestamp=datetime.now(timezone.utc))

    quotes.get_quote.side_effect = changing_quote
    with pytest.raises(ValueError, match="changed during risk snapshot"):
        await broker.account.get_risk_state("PAPER")


async def test_unknown_or_unresolved_account_cannot_claim_context(ledger):
    store, db = ledger
    with pytest.raises(ValueError, match="not initialized"):
        await store.get_risk_state("MISSING", None)
    await db.execute(
        "INSERT INTO paper_orders (order_id, account_id, symbol, side, quantity, status, filled_quantity) VALUES ('pending','PAPER','TEST','BUY',1,'SUBMITTED',0)"
    )
    await db.commit()
    with pytest.raises(ValueError, match="unresolved orders"):
        await store.get_risk_state("PAPER", None)


async def test_owned_connection_does_not_rollback_other_stores(tmp_path, monkeypatch):
    async with aiosqlite.connect(tmp_path / "shared.db") as application_db:
        application_db.row_factory = aiosqlite.Row
        store = PaperStore(application_db)
        await store.init_tables()
        try:
            assert await store._get_db() is not application_db
            await application_db.execute("CREATE TABLE unrelated (value TEXT)")
            await application_db.commit()
            await application_db.execute("INSERT INTO unrelated VALUES ('keep')")
            # A busy dedicated connection must never roll back the application writer.
            await (await store._get_db()).execute("PRAGMA busy_timeout=1")
            broker, quotes, symbol = make_broker(store)
            result = await submit(broker, symbol, OrderSide.BUY)
            assert result.status.value == "REJECTED"
            assert result.filled_quantity == 0
            assert application_db.in_transaction
            row = await (
                await application_db.execute("SELECT value FROM unrelated")
            ).fetchone()
            assert row[0] == "keep"
            await application_db.rollback()
        finally:
            await store.close()


async def test_memory_connection_preexisting_transaction_is_not_rolled_back():
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row
        store = PaperStore(db)
        await store.init_tables()
        await db.execute(
            "UPDATE paper_accounts SET cash=12345 WHERE account_id='PAPER'"
        )
        broker, quotes, symbol = make_broker(store)
        result = await submit(broker, symbol, OrderSide.BUY)
        assert result.status.value == "REJECTED"
        assert result.filled_quantity == 0
        assert db.in_transaction
        assert (await store.get_balance("PAPER")).cash == 12345
        await db.rollback()
        await store.close()


async def test_carry_fee_cannot_commit_a_half_written_fill(ledger, monkeypatch):
    import asyncio

    store, db = ledger
    broker, quotes, symbol = make_broker(store)
    started, release = asyncio.Event(), asyncio.Event()
    original = store.save_order

    async def paused_save(*args, **kwargs):
        started.set()
        await release.wait()
        raise RuntimeError("rollback fill")

    monkeypatch.setattr(store, "save_order", paused_save)
    fill = asyncio.create_task(submit(broker, symbol, OrderSide.BUY))
    await started.wait()
    fees = asyncio.create_task(
        broker.account.apply_carry_fees([], daily_rate=D("0.01"))
    )
    await asyncio.sleep(0)
    assert not fees.done()
    release.set()
    with pytest.raises(RuntimeError, match="rollback fill"):
        await fill
    await fees
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_trade_count == 0
    assert state.context.positions == []
    assert state.context.balance.cash == 100000


@pytest.mark.parametrize("side,limit", [(OrderSide.BUY, "1"), (OrderSide.SELL, "1000")])
async def test_unmarketable_limits_cannot_manufacture_pnl(ledger, side, limit):
    store, db = ledger
    broker, quotes, symbol = make_broker(store, price="200")
    result = await broker.orders.place_order(
        "PAPER", LimitOrder(symbol, side, D("40"), "PAPER", limit_price=D(limit))
    )
    assert result.status.value == "SUBMITTED"
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_trade_count == 1
    assert state.context.balance.cash == 100000
    assert state.context.positions == []


async def test_marketable_limit_fills_quote_and_caps_slippage(ledger):
    store, db = ledger
    broker, quotes, symbol = make_broker(store, price="100")
    broker.orders._estimate_slippage = AsyncMock(return_value=D("110"))
    result = await broker.orders.place_order(
        "PAPER",
        LimitOrder(symbol, OrderSide.BUY, D("2"), "PAPER", limit_price=D("101")),
    )
    assert result.avg_fill_price == 101
    broker.orders._estimate_slippage.assert_awaited_once_with(
        symbol, D("2"), OrderSide.BUY, D("100")
    )


async def test_untriggered_stop_rests_without_filling(ledger):
    from broker.models import StopOrder

    store, db = ledger
    broker, quotes, symbol = make_broker(store)
    result = await broker.orders.place_order(
        "PAPER", StopOrder(symbol, OrderSide.BUY, D("2"), "PAPER", stop_price=D("200"))
    )
    assert result.status.value == "SUBMITTED"
    assert (await broker.account.get_risk_state("PAPER")).context.daily_trade_count == 1


async def test_fill_event_and_order_share_one_utc_timestamp(ledger, monkeypatch):
    store, db = ledger
    broker, quotes, symbol = make_broker(store)
    original_save = store.save_order

    async def change_event_time_then_save(*args, **kwargs):
        await db.execute(
            "UPDATE paper_risk_events SET occurred_at='2026-11-11T23:59:59.999999+00:00' WHERE kind='fill'"
        )
        await original_save(*args, **kwargs)

    monkeypatch.setattr(store, "save_order", change_event_time_then_save)
    await submit(broker, symbol, OrderSide.BUY)
    event = await (
        await db.execute("SELECT occurred_at FROM paper_risk_events WHERE kind='fill'")
    ).fetchone()
    order = await (await db.execute("SELECT created_at FROM paper_orders")).fetchone()
    assert order[0] == event[0]


async def test_ensure_account_preserves_balance_and_reset_changes_epoch(ledger):
    store, db = ledger
    await store.ensure_account("NEW", 100)
    await store.ensure_account("NEW", 1000)
    before = await store.get_risk_state("NEW", None)
    assert before.context.balance.cash == 100
    assert before.symbol_identity == "ticker_asset"
    broker, quotes, symbol = make_broker(store)
    first_epoch = (await broker.account.get_risk_state("PAPER")).epoch
    await broker.reset()
    assert (await broker.account.get_risk_state("PAPER")).epoch != first_epoch


async def test_application_commit_cannot_commit_partial_paper_fill(
    tmp_path, monkeypatch
):
    async with aiosqlite.connect(tmp_path / "shared-commit.db") as application_db:
        application_db.row_factory = aiosqlite.Row
        store = PaperStore(application_db)
        await store.init_tables()
        try:
            broker, quotes, symbol = make_broker(store)

            async def commit_other_connection_then_fail(*args, **kwargs):
                await application_db.commit()
                raise RuntimeError("order write failed after unrelated commit")

            monkeypatch.setattr(store, "save_order", commit_other_connection_then_fail)
            with pytest.raises(RuntimeError, match="order write failed"):
                await submit(broker, symbol, OrderSide.BUY)
            assert (await store.get_balance("PAPER")).cash == 100000
            assert await store.get_positions("PAPER") == []
            assert (
                await broker.account.get_risk_state("PAPER")
            ).context.daily_trade_count == 0
            row = await (
                await application_db.execute("SELECT COUNT(*) FROM paper_risk_events")
            ).fetchone()
            assert row[0] == 0
        finally:
            await store.close()
