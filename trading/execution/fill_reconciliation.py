"""Durable, paper-only projection of accepted fills into tracked positions.

This worker observes persisted venue evidence. It never submits, cancels, resumes,
or advances matching. Jobs are written before dispatch to survive a lost reply.
"""

from __future__ import annotations

import asyncio
import json
import logging
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from agents.models import OpportunityStatus
from broker.models import OrderStatus, AssetType
from broker.paper_dispatch import PaperDispatchMixin
from broker.order_terms import decode_order, encode_order
from exits.rules import parse_rule

log = logging.getLogger(__name__)
_TERMINAL = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}


class PaperFillReconciler:
    def __init__(
        self,
        paper_store,
        position_store,
        opportunity_store,
        exit_manager,
        trade_store=None,
    ):
        self.paper = paper_store
        self.positions = position_store
        self.opportunities = opportunity_store
        self.exits = exit_manager
        self.trade_store = trade_store
        self._lock = asyncio.Lock()

    async def initialize(self):
        await self.positions.init_tables()
        async with self.paper.transaction() as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS paper_fill_jobs (
                job_id TEXT PRIMARY KEY, broker_id TEXT NOT NULL,
                account_id TEXT NOT NULL, signal_id TEXT NOT NULL UNIQUE,
                order_id TEXT, role TEXT NOT NULL, position_id INTEGER,
                payload TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)""")

    async def prepare_exit(self, opportunity, broker, broker_id):
        """Cancel the entry remainder, project its final fill, then size the exit."""
        if (
            not isinstance(broker.orders, PaperDispatchMixin)
            or broker.orders.store is not self.paper
        ):
            raise ValueError("Entry handoff requires the owning paper broker")
        pid = int(
            opportunity.data.get("tracked_position_id")
            or opportunity.data.get("position_id")
        )
        order = opportunity.suggested_trade
        async with self.paper.transaction() as db:
            pos = await (
                await db.execute("SELECT * FROM tracked_positions WHERE id=?", (pid,))
            ).fetchone()
            if not pos or pos["status"] != "open":
                raise ValueError("Exit position is not open")
            if (pos["broker_id"], pos["account_id"], pos["symbol"]) != (
                broker_id,
                order.account_id,
                order.symbol.ticker,
            ) or pos["side"].upper() == order.side.value:
                raise ValueError("Exit handoff position identity mismatch")
            jobs = await (
                await db.execute(
                    "SELECT * FROM paper_fill_jobs WHERE done=0 AND (position_id=? OR job_id=?)",
                    (pid, pos["opportunity_id"]),
                )
            ).fetchall()
            if any(job["role"] != "entry" for job in jobs) or len(jobs) > 1:
                raise ValueError("Position has an outstanding exit")
            entry = await (
                await db.execute(
                    "SELECT payload FROM paper_fill_jobs WHERE job_id=? AND role=?",
                    (pos["opportunity_id"], "entry"),
                )
            ).fetchone()
            epoch = json.loads(entry["payload"])["epoch"] if entry else None
            if epoch:
                generation = await self.paper.account_generation(order.account_id)
                if not generation or generation != epoch:
                    raise ValueError("Tracked entry generation changed")
            if jobs:
                job = jobs[0]
                epoch = json.loads(job["payload"])["epoch"]
                generation = await self.paper.account_generation(job["account_id"])
                if not generation or generation != epoch:
                    raise ValueError("Entry handoff generation changed")
                if not job["order_id"] or (job["broker_id"], job["account_id"]) != (
                    broker_id,
                    order.account_id,
                ):
                    raise ValueError("Entry handoff lacks authoritative order identity")
                snap = await self.paper.get_order_snapshot(job["order_id"])
                if (
                    snap is None
                    or snap.order.signal_id != job["signal_id"]
                    or snap.order.symbol != order.symbol
                ):
                    raise ValueError("Entry handoff order identity mismatch")
                await db.execute("""CREATE TABLE IF NOT EXISTS paper_entry_exit_handoffs (
                    position_id INTEGER PRIMARY KEY, entry_job_id TEXT NOT NULL,
                    epoch TEXT NOT NULL, status TEXT NOT NULL)""")
                await db.execute(
                    "INSERT INTO paper_entry_exit_handoffs (position_id,entry_job_id,epoch,status) VALUES (?,?,?,'cancelling') ON CONFLICT(position_id) DO UPDATE SET status='cancelling'",
                    (pid, job["job_id"], epoch),
                )
                await broker.orders.cancel_order(job["order_id"])
                if (
                    await self.paper.get_order_snapshot(job["order_id"])
                ).status not in _TERMINAL:
                    raise ValueError("Entry cancellation is not terminal")
        await self.reconcile_once()
        async with self.paper.transaction() as db:
            if epoch:
                generation = await self.paper.account_generation(order.account_id)
                if not generation or generation != epoch:
                    raise ValueError("Entry generation changed during handoff")
            pending = await (
                await db.execute(
                    "SELECT job_id FROM paper_fill_jobs WHERE done=0 AND (position_id=? OR job_id=?)",
                    (pid, pos["opportunity_id"]),
                )
            ).fetchone()
            if pending:
                raise ValueError("Entry fill reconciliation is incomplete")
            current = await (
                await db.execute("SELECT * FROM tracked_positions WHERE id=?", (pid,))
            ).fetchone()
            if not current or current["status"] != "open":
                raise ValueError("Exit position is no longer open")
            quantity = Decimal(current["remaining_quantity"])
            if not quantity.is_finite() or quantity <= 0:
                raise ValueError("Exit has no confirmed quantity")
            if jobs:
                await db.execute(
                    "UPDATE paper_entry_exit_handoffs SET status='ready' WHERE position_id=?",
                    (pid,),
                )
            opportunity.suggested_trade = deepcopy(order)
            opportunity.suggested_trade.quantity = (
                quantity
                if jobs or opportunity.data.get("close_full_position")
                else min(order.quantity, quantity)
            )

    async def register(self, opportunity, broker, *, exit_rules=None, broker_id=None):
        """Return a correlated order copy, or None for an already registered job."""
        if not isinstance(broker.orders, PaperDispatchMixin):
            raise ValueError("Fill reconciliation requires a paper broker")
        broker_id = (
            broker_id
            or opportunity.broker_id
            or {
                "PAPER": "paper",
                "KALSHI_PAPER": "kalshi_paper",
                "POLYMARKET_PAPER": "polymarket_paper",
            }[broker.orders.paper_account_id]
        )
        order = deepcopy(opportunity.suggested_trade)
        role = "exit" if opportunity.is_exit else "entry"
        position_id = (
            (
                opportunity.data.get("tracked_position_id")
                or opportunity.data.get("position_id")
            )
            if opportunity.is_exit
            else None
        )
        if role == "exit" and not position_id:
            raise ValueError("Tracked exit requires a position identity")
        contract_expiry = None
        if role == "entry" and order.symbol.asset_type == AssetType.PREDICTION:
            try:
                details = await broker.market_data.get_contract_details(order.symbol)
                if isinstance(details.expires_at, datetime):
                    contract_expiry = details.expires_at.isoformat()
            except Exception:
                log.warning("Prediction expiry unavailable for %s", order.symbol.ticker)
        order.signal_id = "paper-fill:" + uuid4().hex
        async with self.paper.transaction() as db:
            existing = await (
                await db.execute(
                    "SELECT job_id FROM paper_fill_jobs WHERE job_id=?",
                    (str(opportunity.id),),
                )
            ).fetchone()
            if existing:
                return None
            coverage = await self.paper.account_generation(order.account_id)
            if not coverage:
                raise ValueError("Paper account has no execution generation")
            if role == "exit":
                owning_entry = await (
                    await db.execute(
                        "SELECT payload FROM paper_fill_jobs WHERE job_id=(SELECT opportunity_id FROM tracked_positions WHERE id=?) AND role='entry'",
                        (int(position_id),),
                    )
                ).fetchone()
                if (
                    owning_entry
                    and json.loads(owning_entry["payload"])["epoch"]
                    != coverage
                ):
                    raise ValueError("Tracked exit generation changed")
                position = await (
                    await db.execute(
                        "SELECT * FROM tracked_positions WHERE id=?",
                        (int(position_id),),
                    )
                ).fetchone()
                if not position or position["status"] != "open":
                    raise ValueError("Exit position is not open")
                if (
                    position["broker_id"],
                    position["account_id"],
                    position["symbol"],
                ) != (broker_id, order.account_id, order.symbol.ticker):
                    raise ValueError("Exit does not own tracked position")
                if position[
                    "side"
                ].upper() == order.side.value or order.quantity > Decimal(
                    position["remaining_quantity"]
                ):
                    raise ValueError("Exit side or remaining quantity mismatch")
                pending = await (
                    await db.execute(
                        "SELECT job_id FROM paper_fill_jobs WHERE done=0 AND (position_id=? OR job_id=?)",
                        (int(position_id), position["opportunity_id"]),
                    )
                ).fetchone()
                if pending:
                    raise ValueError(
                        "Tracked position already has an outstanding execution"
                    )
            payload = {
                "order": encode_order(order),
                "epoch": coverage,
                "agent_name": opportunity.agent_name,
                "exit_reason": opportunity.data.get("exit_rule", "exit_position"),
                "exit_rules": exit_rules or [],
                "expires_at": contract_expiry,
            }
            await db.execute(
                """INSERT INTO paper_fill_jobs
                (job_id,broker_id,account_id,signal_id,role,position_id,payload)
                VALUES (?,?,?,?,?,?,?)""",
                (
                    str(opportunity.id),
                    broker_id,
                    order.account_id,
                    order.signal_id,
                    role,
                    int(position_id) if position_id else None,
                    json.dumps(payload, default=str, sort_keys=True),
                ),
            )
        return order

    async def rejected(self, job_id):
        """Only for a definite non-acceptance, never for an uncertain response."""
        async with self.paper.transaction() as db:
            await db.execute(
                "UPDATE paper_fill_jobs SET done=1 WHERE job_id=? AND order_id IS NULL",
                (str(job_id),),
            )

    async def reconcile_once(self):
        async with self._lock:
            async with self.paper.transaction() as db:
                jobs = await (
                    await db.execute(
                        "SELECT * FROM paper_fill_jobs WHERE done=0 ORDER BY job_id"
                    )
                ).fetchall()
            for job in jobs:
                try:
                    await self._reconcile(dict(job))
                except Exception:
                    # Keep the job durable and pending. A bad receipt must not stop
                    # unrelated accounts or be mistaken for an executed trade.
                    log.exception(
                        "Paper fill reconciliation pending for %s", job["job_id"]
                    )

    async def run(self, interval=1.0):
        while True:
            await self.reconcile_once()
            await asyncio.sleep(interval)

    async def _reconcile(self, job):
        payload = json.loads(job["payload"])
        expected = decode_order(payload["order"])
        async with self.paper.transaction() as db:
            generation = await self.paper.account_generation(job["account_id"])
            if not generation or generation != payload["epoch"]:
                raise ValueError(
                    "Paper generation changed; fill job requires investigation"
                )
            rows = await self.paper.order_terms_for_account(job["account_id"])
            matches = [
                r
                for r in rows
                if decode_order(json.loads(r["order_payload"])).signal_id == job["signal_id"]
            ]
            if not matches:
                # Recovery may have fenced a request before acceptance. Only its
                # durable rejection is authority to release a pending projection.
                rejected = await self.paper.submit_receipts(
                    job["account_id"], payload["epoch"]
                )
                for receipt in rejected:
                    request = decode_order(json.loads(receipt["order_payload"]))
                    outcome = PaperDispatchMixin._dispatch_result(receipt)
                    if (
                        request.signal_id == job["signal_id"]
                        and outcome.status == OrderStatus.REJECTED
                        and outcome.filled_quantity == 0
                    ):
                        await db.execute(
                            "UPDATE opportunities SET status=?,updated_at=datetime('now') WHERE id=?",
                            (OpportunityStatus.REJECTED.value, job["job_id"]),
                        )
                        await db.execute(
                            "UPDATE paper_fill_jobs SET done=1 WHERE job_id=?",
                            (job["job_id"],),
                        )
                        break
                return  # Otherwise leave uncertain, never infer rejection from absence.
            if len(matches) != 1:
                raise ValueError("Ambiguous paper fill identity")
            order_id = matches[0]["order_id"]
            if job["order_id"] and job["order_id"] != order_id:
                raise ValueError("Paper fill identity changed")
            snapshot = await self.paper.get_order_snapshot(order_id)
            result = await self.paper.get_order_result(order_id)
            # Immediate fills predate detailed fill events. Their dispatch receipt
            # contains the original fee/time, committed with the fill itself.
            if result.filled_quantity > 0 and result.filled_at is None:
                receipts = await self.paper.submit_receipts(job["account_id"])
                for receipt in receipts:
                    original = PaperDispatchMixin._dispatch_result(receipt)
                    if (
                        original.order_id == order_id
                        and original.filled_quantity == result.filled_quantity
                    ):
                        result = replace(
                            result,
                            commission=original.commission,
                            filled_at=original.filled_at,
                        )
                        break
            actual = snapshot.order
            if (actual.account_id, actual.symbol, actual.side, actual.signal_id) != (
                expected.account_id,
                expected.symbol,
                expected.side,
                expected.signal_id,
            ):
                raise ValueError("Paper fill terms do not match registered execution")
            await db.execute(
                "UPDATE paper_fill_jobs SET order_id=? WHERE job_id=?",
                (order_id, job["job_id"]),
            )
        position = None
        if result.filled_quantity > 0:
            common = dict(
                broker_id=job["broker_id"],
                account_id=job["account_id"],
                order_id=order_id,
                expected_epoch=payload["epoch"],
                cumulative_quantity=result.filled_quantity,
                cumulative_avg_price=result.avg_fill_price,
                cumulative_fees=result.commission,
                filled_at=result.filled_at or datetime.now(timezone.utc),
            )
            if job["role"] == "entry":
                position = await self.positions.apply_entry_fill(
                    **common,
                    agent_name=payload["agent_name"],
                    opportunity_id=job["job_id"],
                    symbol=actual.symbol.ticker,
                    side=actual.side.value.lower(),
                    expires_at=payload.get("expires_at"),
                )
            else:
                position = await self.positions.apply_exit_fill(
                    int(job["position_id"]),
                    **common,
                    exit_reason=payload["exit_reason"],
                )
            async with self.paper.transaction() as db:
                await db.execute(
                    "UPDATE paper_fill_jobs SET position_id=? WHERE job_id=?",
                    (position["id"], job["job_id"]),
                )
            rules = []
            if job["role"] == "entry":
                rules = [parse_rule(r) for r in payload["exit_rules"]]
                if not rules:
                    rules = self.exits.compute_default_exits(
                        side=actual.side.value,
                        entry_price=Decimal(str(position["entry_price"])),
                        asset_type=actual.symbol.asset_type,
                        contract_expires_at=datetime.fromisoformat(
                            payload["expires_at"]
                        )
                        if payload.get("expires_at")
                        else None,
                    )
                if any(r is None for r in rules):
                    raise ValueError("Invalid registered exit rule")
            await self.exits.reconcile_position(position["id"], rules)
        # Receipt projection and job completion are one transaction. A worker
        # observing an older cumulative fill cannot overwrite a newer projection.
        async with self.paper.transaction() as db:
            current_generation = await self.paper.account_generation(job["account_id"])
            if (
                not current_generation
                or current_generation != payload["epoch"]
            ):
                raise ValueError("Paper generation changed during fill projection")
            current_job = await (
                await db.execute(
                    "SELECT done FROM paper_fill_jobs WHERE job_id=?", (job["job_id"],)
                )
            ).fetchone()
            if current_job["done"]:
                return
            if position:
                receipt = await (
                    await db.execute(
                        "SELECT quantity FROM tracked_fill_receipts WHERE broker_id=? AND account_id=? AND order_id=?",
                        (job["broker_id"], job["account_id"], order_id),
                    )
                ).fetchone()
                if (
                    not receipt
                    or Decimal(receipt["quantity"]) != result.filled_quantity
                ):
                    return
            stored = await (
                await db.execute(
                    "SELECT data FROM opportunities WHERE id=?", (job["job_id"],)
                )
            ).fetchone()
            if stored is None:
                raise ValueError("Registered opportunity missing")
            data = (
                json.loads(stored["data"])
                if isinstance(stored["data"], str)
                else dict(stored["data"])
            )
            data["execution_receipt"] = {
                "order_id": order_id,
                "status": result.status.value,
                "filled_quantity": str(result.filled_quantity),
                "avg_fill_price": str(result.avg_fill_price)
                if result.avg_fill_price is not None
                else None,
                "commission": str(result.commission),
                "requires_fill_reconciliation": result.status not in _TERMINAL,
            }
            if position:
                data["tracked_position_id"] = position["id"]
            terminal = result.status in _TERMINAL
            status = (
                (
                    OpportunityStatus.EXECUTED
                    if result.filled_quantity > 0
                    else OpportunityStatus.REJECTED
                )
                if terminal
                else OpportunityStatus.RECONCILIATION_REQUIRED
            )
            await db.execute(
                "UPDATE opportunities SET data=?,status=?,updated_at=datetime('now') WHERE id=?",
                (json.dumps(data), status.value, job["job_id"]),
            )
            if self.trade_store is not None:
                recorded = await (
                    await db.execute(
                        "SELECT id FROM trade_executions WHERE opportunity_id=?",
                        (job["job_id"],),
                    )
                ).fetchone()
                receipt_json = json.dumps(data["execution_receipt"])
                if recorded:
                    await db.execute(
                        "UPDATE trade_executions SET order_result=? WHERE opportunity_id=?",
                        (receipt_json, job["job_id"]),
                    )
                else:
                    await db.execute(
                        "INSERT INTO trade_executions (opportunity_id,order_result,risk_evaluation,agent_name) VALUES (?,?,?,?)",
                        (
                            job["job_id"],
                            receipt_json,
                            json.dumps({"passed": True}),
                            payload["agent_name"],
                        ),
                    )
            if terminal:
                await db.execute(
                    "UPDATE paper_fill_jobs SET done=1 WHERE job_id=?", (job["job_id"],)
                )
