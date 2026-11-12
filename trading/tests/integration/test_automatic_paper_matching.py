"""Managed paper progression without explicit matching ticks."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from broker.models import Quote, OrderStatus, TIF, OrderSide
from execution.paper_driver import PaperMatchingDriver
from tests.integration.test_dispatch_recovery import paper, control
from tests.integration.test_paper_fill_reconciliation import (
    projection,
    opportunity,
    submit,
)
from tests.integration.test_paper_resting_recovery import make_rig

pytestmark = pytest.mark.integration


async def setup(projection, paper, control, venue="primary"):
    worker, positions, exits, opps = projection
    broker, svc, order, quotes = make_rig(paper, control, venue)
    await paper.ensure_account(order.account_id, 100000)
    order.quantity = D(2)
    receipt = await submit(worker, opps, svc, broker, opportunity(order))
    driver = PaperMatchingDriver(
        paper, {"paper": broker}, control, worker, interval_seconds=0.05
    )
    await driver.initialize()
    # Query provider via paper wrapper after acceptance; no manual tick delivery.
    broker.market_data.get_quote = AsyncMock(
        side_effect=lambda symbol: Quote(
            symbol, bid=order.limit_price, ask=order.limit_price, last=order.limit_price
        )
    )
    return driver, broker, order, receipt, positions


@pytest.mark.parametrize("venue", ["primary", "simulated", "kalshi", "polymarket"])
async def test_run_progresses_partial_to_full_and_tracks_without_ticks(
    projection, paper, control, venue
):
    driver, broker, order, receipt, positions = await setup(
        projection, paper, control, venue
    )
    task = asyncio.create_task(driver.run())
    try:
        async with asyncio.timeout(4):
            while (
                await paper.get_order_result(receipt.order_id)
            ).status != OrderStatus.FILLED:
                await asyncio.sleep(0.02)
            while not await positions.list_open():
                await asyncio.sleep(0.02)
        result = await paper.get_order_result(receipt.order_id)
        assert result.filled_quantity == 2
        async with paper.transaction() as db:
            fills = await (
                await db.execute(
                    "SELECT quantity FROM paper_fill_events WHERE order_id=?",
                    (receipt.order_id,),
                )
            ).fetchall()
        assert [D(f["quantity"]) for f in fills] == [D(1), D(1)]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert task.done()


async def test_same_quote_and_competing_workers_cannot_replenish_liquidity(
    projection, paper, control
):
    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    quote = Quote(order.symbol, bid=D(99), ask=D(99), last=D(99), volume=99999999)
    broker.market_data.get_quote = AsyncMock(return_value=quote)
    other = PaperMatchingDriver(paper, {"alias": broker}, control)
    await other.initialize()
    await asyncio.gather(driver.cycle(), other.cycle())
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == 1
    # Replay still cannot spend this observation after restart/another second.
    await asyncio.sleep(1.05)
    await other.cycle()
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == 1


@pytest.mark.parametrize("bad", ["stale", "crossed", "missing", "mismatch", "error"])
async def test_bad_data_does_not_fill_and_worker_recovers(
    projection, paper, control, bad
):
    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    quote = Quote(order.symbol, bid=D(99), ask=D(99), last=D(99))
    if bad == "stale":
        quote = replace(quote, timestamp=quote.timestamp - timedelta(minutes=1))
    if bad == "crossed":
        quote = replace(quote, bid=D(100))
    if bad == "missing":
        quote = replace(quote, ask=None)
    if bad == "mismatch":
        quote = replace(quote, symbol=replace(order.symbol, ticker="WRONG"))
    broker.market_data.get_quote = AsyncMock(
        return_value=quote,
        side_effect=RuntimeError("unavailable") if bad == "error" else None,
    )
    await driver.cycle()
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == 0
    broker.market_data.get_quote = AsyncMock(
        side_effect=lambda symbol: Quote(symbol, bid=D(99), ask=D(99), last=D(99))
    )
    await driver.cycle()
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == 1


@pytest.mark.parametrize("state", ["true", None])
async def test_halt_or_missing_control_blocks_matching_but_not_expiry(
    projection, paper, control, state
):
    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    if state is None:
        await control.delete("kill_switch:active")
    else:
        await control.set("kill_switch:active", state)
    await driver.cycle()
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == 0
    # Make it a previous-day DAY order; no quote or tick required to expire.
    async with paper.transaction() as db:
        snapshot = await paper.get_order_snapshot(receipt.order_id)
        snapshot.order.time_in_force = TIF.DAY
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        from execution.service import _encode
        import json

        await db.execute(
            "UPDATE paper_order_terms SET order_payload=?,submitted_at=? WHERE order_id=?",
            (
                json.dumps(_encode(snapshot.order), default=str),
                yesterday.isoformat(),
                receipt.order_id,
            ),
        )
        await db.execute(
            "UPDATE paper_orders SET created_at=? WHERE order_id=?",
            (yesterday.isoformat(), receipt.order_id),
        )
    broker.market_data.get_quote = AsyncMock(side_effect=RuntimeError("no feed"))
    await driver.cycle()
    assert (
        await paper.get_order_result(receipt.order_id)
    ).status == OrderStatus.CANCELLED
    broker.market_data.get_quote.assert_not_awaited()


async def test_live_and_foreign_ledger_managers_are_excluded(
    projection, paper, control
):
    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    live = SimpleNamespace(
        orders=SimpleNamespace(cancel_order=AsyncMock(), process_tick=AsyncMock()),
        market_data=SimpleNamespace(get_quote=AsyncMock()),
    )
    safe = PaperMatchingDriver(
        paper, {"live": live, "paper": broker, "alias": broker}, control
    )
    assert safe.brokers == [broker]
    await safe.initialize()
    await safe.cycle()
    live.orders.process_tick.assert_not_awaited()
    live.market_data.get_quote.assert_not_awaited()


@pytest.mark.parametrize("allow_last", [True, False])
async def test_explicit_last_only_simulation_policy(
    projection, paper, control, allow_last
):
    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    driver.allow_last_price = allow_last
    broker.market_data.get_quote = AsyncMock(
        return_value=Quote(order.symbol, last=order.limit_price)
    )
    await driver.cycle()
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == (
        1 if allow_last else 0
    )


async def test_control_read_timeout_inside_transaction_releases_ledger(
    projection, paper, control
):
    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    calls = 0
    original = control.get

    async def get(key):
        nonlocal calls
        calls += 1
        if calls == 2:
            await asyncio.Event().wait()
        return await original(key)

    driver.controls = SimpleNamespace(get=get)
    driver.timeout = 0.02
    async with asyncio.timeout(1):
        await driver.cycle()
        # Cancellation acquiring ledger proves hung control read released it.
        await broker.orders.cancel_order(receipt.order_id)
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == 0


async def test_matching_failure_retries_same_quote_without_spending_budget(
    projection, paper, control
):
    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    quote = Quote(order.symbol, bid=D(99), ask=D(99), last=D(99))
    broker.market_data.get_quote = AsyncMock(return_value=quote)
    original = paper.save_order
    paper.save_order = AsyncMock(side_effect=RuntimeError("rollback"))
    await driver.cycle()
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == 0
    paper.save_order = original
    await driver.cycle()
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == 1


async def test_reset_while_quote_is_in_flight_cannot_apply_old_generation(
    projection, paper, control
):
    driver, broker, order, receipt, positions = await setup(projection, paper, control)

    async def quote(symbol):
        await broker.reset()
        return Quote(symbol, bid=D(99), ask=D(99), last=D(99))

    broker.market_data.get_quote = quote
    await driver.cycle()
    async with paper.transaction() as db:
        count = await (
            await db.execute("SELECT COUNT(*) AS n FROM paper_auto_ticks")
        ).fetchone()
    assert count["n"] == 0
    assert await broker.account.get_positions("PAPER") == []


async def test_expiry_preserves_partial_fills_fees_and_gtc(projection, paper, control):
    from execution.service import _encode
    import json

    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    await driver.cycle()
    from copy import deepcopy
    from tests.integration.test_dispatch_recovery import service

    gtc = deepcopy(order)
    gtc.limit_price = D(98)
    gtc_receipt = await service(broker, control).submit(broker, order.account_id, gtc)
    async with paper.transaction() as db:
        snapshot = await paper.get_order_snapshot(receipt.order_id)
        snapshot.order.time_in_force = TIF.DAY
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        await db.execute(
            "UPDATE paper_order_terms SET order_payload=?,submitted_at=? WHERE order_id=?",
            (
                json.dumps(_encode(snapshot.order), default=str),
                yesterday.isoformat(),
                receipt.order_id,
            ),
        )
        await db.execute(
            "UPDATE paper_orders SET created_at=? WHERE order_id=?",
            (yesterday.isoformat(), receipt.order_id),
        )
    await control.set("kill_switch:active", "true")
    await driver.cycle()
    result = await paper.get_order_result(receipt.order_id)
    assert result.status == OrderStatus.CANCELLED and result.filled_quantity == 1
    assert D((await positions.list_open())[0]["remaining_quantity"]) == 1
    assert (
        await paper.get_order_result(gtc_receipt.order_id)
    ).status == OrderStatus.SUBMITTED


async def test_broken_symbol_does_not_stop_other_symbols(projection, paper, control):
    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    from copy import deepcopy
    from broker.models import Symbol
    from tests.integration.test_dispatch_recovery import service

    other = deepcopy(order)
    other.symbol = Symbol("A_FAIL")
    # Use current non-marketable baseline for admission, then fail only that feed.
    provider = broker.market_data.get_quote
    broker.market_data.get_quote = AsyncMock(
        side_effect=lambda symbol: Quote(symbol, bid=D(100), ask=D(100), last=D(100))
    )
    await service(broker, control).submit(broker, order.account_id, other)

    async def quote(symbol):
        if symbol == other.symbol:
            raise RuntimeError("bad symbol")
        return Quote(symbol, bid=D(99), ask=D(99), last=D(99))

    broker.market_data.get_quote = quote
    await driver.cycle()
    assert (await paper.get_order_result(receipt.order_id)).filled_quantity == 1


async def test_clock_expiry_runs_while_quote_lookup_is_waiting(
    projection, paper, control
):
    from execution.service import _encode
    import json

    driver, broker, order, receipt, positions = await setup(projection, paper, control)
    waiting = asyncio.Event()

    async def stuck(symbol):
        waiting.set()
        await asyncio.Event().wait()

    broker.market_data.get_quote = stuck
    driver.timeout = 2
    task = asyncio.create_task(driver.run())
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        async with paper.transaction() as db:
            snapshot = await paper.get_order_snapshot(receipt.order_id)
            snapshot.order.time_in_force = TIF.DAY
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            await db.execute(
                "UPDATE paper_order_terms SET order_payload=?,submitted_at=? WHERE order_id=?",
                (
                    json.dumps(_encode(snapshot.order), default=str),
                    yesterday.isoformat(),
                    receipt.order_id,
                ),
            )
            await db.execute(
                "UPDATE paper_orders SET created_at=? WHERE order_id=?",
                (yesterday.isoformat(), receipt.order_id),
            )
        async with asyncio.timeout(0.8):
            while (
                await paper.get_order_result(receipt.order_id)
            ).status != OrderStatus.CANCELLED:
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not [
        t
        for t in asyncio.all_tasks()
        if t.get_name() == "paper_order_expiry" and not t.done()
    ]
