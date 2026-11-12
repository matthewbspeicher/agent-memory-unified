"""Idempotent paper dispatch and late-delivery fencing on the paper transaction."""

import json
from dataclasses import asdict
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

from broker.models import OrderResult, OrderStatus
from broker.order_terms import decode_order, order_payload
from broker.paper_matching import PaperMatchingMixin
from execution.context import OrderSnapshot
from execution.dispatch import DispatchEvidence


class PaperDispatchMixin(PaperMatchingMixin):
    async def submit_dispatch(self, account_id, order, dispatch_id, epoch):
        from storage.paper import PaperWriteNotStarted

        try:
            return await self._submit_dispatch(account_id, order, dispatch_id, epoch)
        except PaperWriteNotStarted as exc:
            return OrderResult("", OrderStatus.REJECTED, message=str(exc))

    async def _submit_dispatch(self, account_id, order, dispatch_id, epoch):
        payload = order_payload(order)
        async with self._store.transaction() as db:
            await self._dispatch_epoch(account_id, epoch)
            row = await self._store.get_dispatch(dispatch_id)
            if row:
                self._match_dispatch(row, account_id, payload, epoch)
                return self._dispatch_result(row)
            if order.signal_id:
                from storage.postgres import PostgresDB

                if isinstance(db, PostgresDB):
                    table = await db.fetchone(
                        "SELECT to_regclass('paper_fill_jobs') AS name"
                    )
                    exists = table and table["name"] is not None
                else:
                    exists = await (
                        await db.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_fill_jobs'"
                        )
                    ).fetchone()
                if exists:
                    job = await (
                        await db.execute(
                            "SELECT payload FROM paper_fill_jobs WHERE signal_id=?",
                            (order.signal_id,),
                        )
                    ).fetchone()
                    if job and json.loads(job["payload"])["epoch"] != epoch:
                        return OrderResult(
                            "",
                            OrderStatus.REJECTED,
                            message="Registered execution generation changed",
                        )
            result = await self.place_order(account_id, order)
            await self._store.insert_dispatch(
                dispatch_id,
                account_id,
                payload,
                epoch,
                json.dumps(asdict(result), default=str),
            )
            return result

    async def amend_dispatch(self, order_id, changes, dispatch_id, epoch):
        async with self._store.transaction():
            snap = await self._snapshot(order_id)
            await self._dispatch_epoch(snap.order.account_id, epoch)
            row = await self._store.get_dispatch(dispatch_id)
            if row:
                candidate = decode_order(json.loads(row["order_payload"]))
                if row["operation"] != "amend" or row["original_order_id"] != order_id:
                    raise ValueError("Dispatch identity reused for another operation")
                if any(
                    not hasattr(candidate, key) or getattr(candidate, key) != value
                    for key, value in changes.items()
                ):
                    raise ValueError("Dispatch amendment terms differ")
                self._match_dispatch(
                    row,
                    snap.order.account_id,
                    row["order_payload"],
                    epoch,
                    operation="amend",
                    original_order_id=order_id,
                )
                return self._dispatch_result(row)
            candidate = deepcopy(snap.order)
            for key, value in changes.items():
                if not hasattr(candidate, key):
                    raise ValueError("Unsupported amendment field")
                setattr(candidate, key, value)
            payload = order_payload(candidate)
            result = await self.modify_order(order_id, changes)
            await self._store.insert_dispatch(
                dispatch_id,
                candidate.account_id,
                payload,
                epoch,
                json.dumps(asdict(result), default=str),
                "amend",
                order_id,
            )
            return result

    async def reconcile_dispatch(self, attempt):
        if attempt["operation"] not in {"submit", "amend"}:
            raise ValueError("Unsupported dispatch operation")
        order = decode_order(attempt["order"])
        payload = order_payload(order)
        account, epoch = attempt["account"], attempt["epoch"]
        dispatch_id = attempt["dispatch_id"]
        async with self._store.transaction():
            await self._dispatch_epoch(account, epoch)
            row = await self._store.get_dispatch(dispatch_id)
            if row is None:
                # Acquiring the same write lock waits for an in-flight fill. If
                # absent now, persist a tombstone so a late delivery cannot fill.
                result = OrderResult(
                    "", OrderStatus.REJECTED, message="Dispatch fenced by recovery"
                )
                await self._store.insert_dispatch(
                    dispatch_id,
                    account,
                    payload,
                    epoch,
                    json.dumps(asdict(result), default=str),
                    attempt["operation"],
                    attempt.get("order_id"),
                )
            else:
                self._match_dispatch(
                    row,
                    account,
                    payload,
                    epoch,
                    operation=attempt["operation"],
                    original_order_id=attempt.get("order_id"),
                )
                result = self._dispatch_result(row)
            snapshot = None
            if result.order_id:
                snapshot = await self._store.get_order_snapshot(result.order_id)
                if snapshot is None:
                    # Legacy immediate receipts have no full order terms.
                    snapshot = OrderSnapshot(
                        result.order_id, order, result.status, result.filled_quantity
                    )
            return DispatchEvidence(
                dispatch_id,
                account,
                attempt["operation"],
                order,
                attempt.get("order_id"),
                epoch,
                datetime.now(timezone.utc),
                "not_accepted" if result.status == OrderStatus.REJECTED else "applied",
                snapshot,
            )

    async def _dispatch_epoch(self, account, epoch):
        if not epoch or await self._store.account_generation(account) != epoch:
            raise ValueError("Paper dispatch account generation changed")

    @staticmethod
    def _match_dispatch(
        row, account, payload, epoch, *, operation="submit", original_order_id=None
    ):
        if (
            row["operation"] != operation
            or row["original_order_id"] != original_order_id
        ):
            raise ValueError("Dispatch identity reused for another operation")
        if (row["account_id"], row["order_payload"], row["epoch"]) != (
            account,
            payload,
            epoch,
        ):
            raise ValueError("Dispatch identity reused with different order terms")

    @staticmethod
    def _dispatch_result(row):
        data = json.loads(row["result_payload"])
        data["status"] = OrderStatus(data["status"])
        for key in ("filled_quantity", "avg_fill_price", "commission"):
            if data.get(key) is not None:
                data[key] = Decimal(data[key])
        if data.get("filled_at"):
            data["filled_at"] = datetime.fromisoformat(data["filled_at"])
        return OrderResult(**data)
