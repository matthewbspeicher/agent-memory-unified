"""Durable paper acceptance, partial fills and snapshot reconciliation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from broker.models import LimitOrder, Symbol, OrderSide, OrderStatus, Quote
from storage.paper import PaperStore


@pytest.fixture
async def ledger(tmp_path):
    async with aiosqlite.connect(tmp_path / "orders.db") as application:
        application.row_factory = aiosqlite.Row
        store = PaperStore(application)
        await store.init_tables()
        try:
            yield store, await store._get_db()
        finally:
            await store.close()


def order(quantity="3"):
    return LimitOrder(
        Symbol("TEST"), OrderSide.BUY, D(quantity), "PAPER", limit_price=D("100")
    )


def quotes(price="100"):
    return SimpleNamespace(
        get_quote=AsyncMock(
            side_effect=lambda sym: Quote(
                sym, bid=D(price), ask=D(price), last=D(price)
            )
        )
    )


async def accept(store, value, order_id="order", submitted_at=None):
    async with store.transaction():
        await store.save_order_terms(order_id, value, submitted_at=submitted_at)
        await store.save_order(
            order_id,
            value.account_id,
            value.symbol,
            value.side,
            value.quantity,
            "SUBMITTED",
            D("0"),
            None,
        )


async def test_resting_partial_filled_state_survives_restart(ledger):
    store, db = ledger
    value = order()
    await accept(store, value)
    state = await store.get_risk_state("PAPER", quotes())
    assert state.context.daily_trade_count == 1
    assert state.orders[0].status == OrderStatus.SUBMITTED
    assert state.orders[0].filled_quantity == 0
    first = await store.record_simulated_fill(
        "fill1", "order", value, D("1"), D("99"), D("0.5")
    )
    assert first.status == OrderStatus.PARTIAL
    assert first.filled_quantity == 1
    state = await store.get_risk_state("PAPER", quotes("99"))
    assert state.context.daily_trade_count == 1
    assert state.context.daily_pnl == D("-0.5")
    assert state.orders[0].filled_quantity == 1
    restarted = PaperStore(db)
    await restarted.init_tables()
    try:
        snapshot = await restarted.get_order_snapshot("order")
        assert snapshot.order == value
        final = await restarted.record_simulated_fill(
            "fill2", "order", value, D("2"), D("99"), D("1")
        )
        assert final.status == OrderStatus.FILLED
        assert final.filled_quantity == 3
        assert final.avg_fill_price == 99
        assert final.commission == D("1.5")
        state = await restarted.get_risk_state("PAPER", quotes("99"))
        assert not state.orders
        assert "order" in state.terminal_order_ids
        assert state.context.daily_trade_count == 1
        assert state.context.daily_pnl == D("-1.5")
    finally:
        await restarted.close()


async def test_duplicate_fill_id_cannot_double_spend(ledger):
    store, db = ledger
    value = order()
    await accept(store, value)
    await store.record_simulated_fill("fill", "order", value, D("1"), D("99"))
    cash = (await store.get_balance("PAPER")).cash
    with pytest.raises(aiosqlite.IntegrityError):
        await store.record_simulated_fill("fill", "order", value, D("1"), D("99"))
    assert (await store.get_balance("PAPER")).cash == cash
    assert (await store.get_order_result("order")).filled_quantity == 1


async def test_overfill_and_different_terms_reject_before_mutation(ledger):
    store, db = ledger
    value = order()
    await accept(store, value)
    with pytest.raises(ValueError, match="Invalid paper fill"):
        await store.record_simulated_fill("fill", "order", value, D("4"), D("99"))
    with pytest.raises(ValueError, match="terms do not match"):
        await store.record_simulated_fill("fill", "order", order("4"), D("1"), D("99"))
    assert (await store.get_balance("PAPER")).cash == 100000


async def test_ledger_cumulative_quantity_must_match_fill_evidence(ledger):
    store, db = ledger
    value = order()
    await accept(store, value)
    await store.record_simulated_fill("fill", "order", value, D("1"), D("99"))
    await db.execute("UPDATE paper_orders SET filled_quantity=2 WHERE order_id='order'")
    await db.commit()
    with pytest.raises(ValueError, match="cumulative fill evidence"):
        await store.get_risk_state("PAPER", quotes())


async def test_prior_day_acceptance_filled_today_counts_once(ledger):
    store, db = ledger
    value = order()
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    await accept(store, value, submitted_at=yesterday)
    assert (
        await store.get_risk_state("PAPER", quotes())
    ).context.daily_trade_count == 0
    await store.record_simulated_fill("one", "order", value, D("1"), D("99"))
    await store.record_simulated_fill("two", "order", value, D("1"), D("99"))
    assert (
        await store.get_risk_state("PAPER", quotes())
    ).context.daily_trade_count == 1
    assert (await store.get_order_snapshot("order")).submitted_at == yesterday


async def test_amendment_preserves_submission_time_and_trigger(ledger):
    store, db = ledger
    value = order()
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    await accept(store, value, submitted_at=yesterday)
    await db.execute("UPDATE paper_order_terms SET triggered=1 WHERE order_id='order'")
    await db.commit()
    changed = order("4")
    async with store.transaction():
        await store.save_order_terms("order", changed)
        await store.save_order(
            "order",
            "PAPER",
            changed.symbol,
            changed.side,
            changed.quantity,
            "SUBMITTED",
            D("0"),
            None,
        )
    snapshot = await store.get_order_snapshot("order")
    assert snapshot.order.quantity == 4
    assert snapshot.submitted_at == yesterday
    trigger = await (
        await db.execute(
            "SELECT triggered FROM paper_order_terms WHERE order_id='order'"
        )
    ).fetchone()
    assert trigger[0] == 1


async def test_cancelled_unfilled_accepted_order_counts_once_and_is_terminal(ledger):
    store, db = ledger
    value = order()
    await accept(store, value)
    async with store.transaction():
        await store.save_order(
            "order",
            "PAPER",
            value.symbol,
            value.side,
            value.quantity,
            "CANCELLED",
            D("0"),
            None,
        )
    state = await store.get_risk_state("PAPER", quotes())
    assert state.context.daily_trade_count == 1
    assert state.terminal_order_ids == {"order"}
    assert state.orders == []


async def test_open_order_without_terms_fails_closed(ledger):
    store, db = ledger
    value = order()
    async with store.transaction():
        await store.save_order(
            "order",
            "PAPER",
            value.symbol,
            value.side,
            value.quantity,
            "SUBMITTED",
            D("0"),
            None,
        )
    with pytest.raises(ValueError, match="without terms"):
        await store.get_risk_state("PAPER", quotes())


async def test_missing_risk_link_blocks_simulated_fill_evidence(ledger):
    store, db = ledger
    value = order()
    await accept(store, value)
    await store.record_simulated_fill("fill", "order", value, D("1"), D("99"))
    await db.execute("DELETE FROM paper_risk_events WHERE event_id='fill'")
    await db.commit()
    with pytest.raises(ValueError, match="simulated fill evidence"):
        await store.get_risk_state("PAPER", quotes())


async def test_match_tick_replay_is_durable(ledger):
    store, db = ledger
    async with store.transaction():
        await store.save_match_tick("tick", {"consumed_ask": "2"})
    assert await store.get_match_tick("tick") == {"consumed_ask": "2"}
    with pytest.raises(aiosqlite.IntegrityError):
        async with store.transaction():
            await store.save_match_tick("tick", {"consumed_ask": "3"})
    assert await store.get_match_tick("tick") == {"consumed_ask": "2"}


async def test_dispatch_schema_additions_preserve_existing_receipt(ledger):
    store, db = ledger
    await db.execute("DROP TABLE paper_dispatches")
    await db.execute(
        "CREATE TABLE paper_dispatches (dispatch_id TEXT PRIMARY KEY, account_id TEXT, order_payload TEXT, epoch TEXT, result_payload TEXT)"
    )
    await db.execute(
        "INSERT INTO paper_dispatches VALUES ('prior','PAPER','{}','epoch','{}')"
    )
    await db.commit()
    await store.init_tables()
    row = await (
        await db.execute("SELECT * FROM paper_dispatches WHERE dispatch_id='prior'")
    ).fetchone()
    assert row["operation"] == "submit"
    assert row["original_order_id"] is None


@pytest.mark.parametrize(
    "field,value", [("symbol", "OTHER"), ("side", "SELL"), ("status", "FILLED")]
)
async def test_tampered_order_identity_or_status_fails_closed(ledger, field, value):
    store, db = ledger
    await accept(store, order())
    async with store.transaction():
        await db.execute(
            f"UPDATE paper_orders SET {field}=? WHERE order_id='order'", (value,)
        )
    with pytest.raises(ValueError, match="disagree"):
        await store.get_risk_state("PAPER", quotes())


@pytest.mark.parametrize(
    "field,value", [("price", "0"), ("commission", "-1"), ("quantity", "NaN")]
)
async def test_tampered_fill_amounts_fail_closed(ledger, field, value):
    store, db = ledger
    value_order = order()
    await accept(store, value_order)
    await store.record_simulated_fill("fill", "order", value_order, D("1"), D("99"))
    async with store.transaction():
        await db.execute(
            f"UPDATE paper_fill_events SET {field}=? WHERE fill_id='fill'", (value,)
        )
    with pytest.raises(ValueError, match="amounts"):
        await store.get_risk_state("PAPER", quotes())
