"""Managed paper-only matching from quote snapshots with explicit simulated depth."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal

from broker.models import Quote
from broker.paper_dispatch import PaperDispatchMixin

log = logging.getLogger(__name__)


def identity(*values):
    return hashlib.sha256(
        json.dumps(values, default=str, sort_keys=True).encode()
    ).hexdigest()


class PaperMatchingDriver:
    def __init__(
        self,
        paper_store,
        brokers,
        control_store,
        reconciler=None,
        *,
        interval_seconds=1.0,
        liquidity_per_quote=Decimal("1"),
        quote_timeout=5.0,
        allow_last_price=True,
    ):
        if isinstance(liquidity_per_quote, bool):
            raise ValueError("Invalid simulated liquidity")
        self.liquidity = Decimal(str(liquidity_per_quote))
        if not self.liquidity.is_finite() or self.liquidity <= 0:
            raise ValueError("Invalid simulated liquidity")
        if not math.isfinite(interval_seconds) or not 0.05 <= interval_seconds <= 30:
            raise ValueError("Invalid paper matching interval")
        if not math.isfinite(quote_timeout) or quote_timeout <= 0:
            raise ValueError("Invalid quote timeout")
        self.paper, self.controls, self.reconciler = (
            paper_store,
            control_store,
            reconciler,
        )
        self.interval, self.timeout = interval_seconds, quote_timeout
        self.allow_last_price = allow_last_price
        # Never touch a live order manager, or a paper manager owning another ledger.
        self.brokers = []
        seen = set()
        for broker in brokers.values():
            manager = broker.orders
            if (
                isinstance(manager, PaperDispatchMixin)
                and manager.store is paper_store
                and id(manager) not in seen
            ):
                seen.add(id(manager))
                self.brokers.append(broker)

    async def initialize(self):
        async with self.paper.transaction() as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS paper_auto_ticks (
                event_id TEXT PRIMARY KEY, sample_id TEXT NOT NULL UNIQUE)""")

    async def cycle(self):
        active = []
        # Expire every account before awaiting any quote, including during halts.
        for broker in self.brokers:
            try:
                await broker.orders.expire_orders()
                active.append(broker)
            except Exception:
                log.exception(
                    "Paper expiry failed for %s", broker.orders.paper_account_id
                )
        for broker in active:
            try:
                await self._match_account(broker)
            except Exception:
                log.exception(
                    "Paper matching failed for %s", broker.orders.paper_account_id
                )
        if self.reconciler is not None:
            await self.reconciler.reconcile_once()

    async def _match_account(self, broker):
        manager = broker.orders
        async with self.paper.transaction():
            epoch = await self.paper.account_generation(manager.paper_account_id)
            if not epoch:
                return
            symbols = set()
            for order_id in await self.paper.open_order_ids(manager.paper_account_id):
                symbols.add((await manager.order_snapshot(order_id)).order.symbol)
        for symbol in sorted(
            symbols, key=lambda s: json.dumps(asdict(s), default=str, sort_keys=True)
        ):
            try:
                if self.controls is None or await asyncio.wait_for(
                    self.controls.get("kill_switch:active"), self.timeout
                ) not in ("false", b"false"):
                    return
                quote = await asyncio.wait_for(
                    broker.market_data.get_quote(symbol), self.timeout
                )
                if not isinstance(quote, Quote) or quote.symbol != symbol:
                    raise ValueError("Matching quote symbol mismatch")
                if (
                    self.allow_last_price
                    and quote.bid in (None, Decimal(0))
                    and quote.ask in (None, Decimal(0))
                    and isinstance(quote.last, Decimal)
                    and quote.last.is_finite()
                    and quote.last > 0
                ):
                    quote = replace(quote, bid=quote.last, ask=quote.last)

                # Timestamp identifies the observed quote, not price/volume changes
                # that could re-spend one sample. One event per wall-clock second
                # also bounds workers whose providers generate distinct timestamps.
                sample = identity(
                    manager.paper_account_id, epoch, asdict(symbol), quote.timestamp
                )
                async with self.paper.transaction() as db:
                    if (
                        await self.paper.account_generation(manager.paper_account_id)
                        != epoch
                    ):
                        continue
                    if await asyncio.wait_for(
                        self.controls.get("kill_switch:active"), self.timeout
                    ) not in (
                        "false",
                        b"false",
                    ):
                        continue
                    event = identity(
                        manager.paper_account_id,
                        epoch,
                        asdict(symbol),
                        int(datetime.now(timezone.utc).timestamp()),
                    )
                    if await (
                        await db.execute(
                            "SELECT event_id FROM paper_auto_ticks WHERE event_id=? OR sample_id=?",
                            (event, sample),
                        )
                    ).fetchone():
                        continue
                    await manager.process_tick(
                        quote,
                        bid_size=self.liquidity,
                        ask_size=self.liquidity,
                        tick_id="auto:" + event,
                    )
                    await db.execute(
                        "INSERT INTO paper_auto_ticks (event_id,sample_id) VALUES (?,?)",
                        (event, sample),
                    )
            except Exception:
                log.exception(
                    "Paper matching quote rejected for %s/%s",
                    manager.paper_account_id,
                    symbol.ticker,
                )

    async def _expiry_loop(self):
        while True:
            for broker in self.brokers:
                try:
                    await broker.orders.expire_orders()
                except Exception:
                    log.exception(
                        "Paper expiry failed for %s", broker.orders.paper_account_id
                    )
            await asyncio.sleep(self.interval)

    async def run(self):
        # Independent clock loop keeps expiry moving while matching awaits feeds.
        expiry = asyncio.create_task(self._expiry_loop(), name="paper_order_expiry")
        try:
            while True:
                try:
                    await self.cycle()
                except Exception:
                    log.exception("Paper driver cycle failed; retrying")
                await asyncio.sleep(self.interval)
        finally:
            expiry.cancel()
            await asyncio.gather(expiry, return_exceptions=True)
