"""The sole application boundary for broker submissions and amendments.

A durable, non-expiring admission lock serializes account snapshots and pending
reservations across processes. An ambiguous dispatch retains the lock for explicit
reconciliation; a restart must never silently retry an uncertain financial write.
Cancellation deliberately remains outside admission.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
import uuid

from broker.models import (
    AssetType,
    Symbol,
    OrderBase,
    MarketOrder,
    TrailingStopOrder,
    OrderSide,
    OrderStatus,
    Position,
    Quote,
    OrderResult,
    is_stale,
    timestamp_age_seconds,
)
from broker.order_terms import (
    InvalidOrderTerms,
    decode_order,
    encode_order,
    validate_order_terms,
)
from execution.context import AccountRiskState, OrderSnapshot


class ExecutionRejected(RuntimeError):
    """No broker mutation occurred: policy or input rejected the request."""


class ExecutionUnavailable(ExecutionRejected):
    """Admission is unavailable; outcome_unknown forbids assuming rejection."""

    def __init__(self, message, *, outcome_unknown=False):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


_OPEN = {OrderStatus.SUBMITTED, OrderStatus.PARTIAL}
_LOCK = "execution:admission:lock"
_JOURNAL = "execution:admission:reservations"
_ATTEMPT = "execution:admission:attempt"


def _decimal(value, name, *, positive=True):
    if isinstance(value, bool):
        raise ExecutionRejected(f"Invalid {name}")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ExecutionRejected(f"Invalid {name}") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ExecutionRejected(f"Invalid {name}")
    return result


class ExecutionService:
    def __init__(
        self, risk_engine, control_store, *, max_age_seconds=30, timeout_seconds=15
    ):
        self._risk = risk_engine
        self._store = control_store
        self._risk.bind_control_store(control_store)
        self._max_age = max_age_seconds
        self._timeout = timeout_seconds
        self._local_lock = asyncio.Lock()
        self._brokers = {}  # Stable names, not object ids, survive process restart.

    def register_brokers(self, brokers):
        for name, broker in brokers.items():
            if broker is not None:
                self._brokers.setdefault(name, broker)

    def _broker_name(self, broker):
        for name, candidate in self._brokers.items():
            if candidate is broker:
                return name
        raise ExecutionUnavailable("Execution broker is not registered")

    @asynccontextmanager
    async def _admission(self):
        async with self._local_lock:
            async with self._distributed_admission() as receipt:
                yield receipt

    @asynccontextmanager
    async def _distributed_admission(self):
        if self._store is None:
            raise ExecutionUnavailable("Execution control store is unavailable")
        token = str(uuid.uuid4())
        try:
            acquired = await self._store.set(_LOCK, token, nx=True)
        except Exception as exc:
            raise ExecutionUnavailable("Execution admission store unavailable") from exc
        if not acquired:
            raise ExecutionUnavailable("Execution busy or awaiting reconciliation")
        receipt = {"uncertain": False, "token": token}
        try:
            yield receipt
        except ExecutionRejected as exc:
            if receipt["uncertain"]:
                raise ExecutionUnavailable(
                    "Order outcome unknown; execution requires reconciliation",
                    outcome_unknown=True,
                ) from exc
            raise
        except Exception as exc:
            detail = (
                "Order outcome unknown; execution requires reconciliation"
                if receipt["uncertain"]
                else "Execution admission unavailable"
            )
            raise ExecutionUnavailable(
                detail, outcome_unknown=receipt["uncertain"]
            ) from exc
        finally:
            # Once transport starts, failures/timeouts/cancellation can mean an
            # accepted order with no receipt. Only reconciliation may unlock it.
            if not receipt["uncertain"]:
                try:
                    await self._store.eval(
                        """-- execution:release
                        if redis.call('GET', KEYS[1]) == ARGV[1] then
                            return redis.call('DEL', KEYS[1])
                        end
                        return 0
                        """,
                        1,
                        _LOCK,
                        token,
                    )
                except Exception:
                    pass  # A retained lock fails closed, never expires into a retry.

    def _fresh(self, timestamp, what):
        if not isinstance(timestamp, datetime):
            raise ExecutionUnavailable(f"Missing {what} timestamp")
        # Existing Quote providers use local naive datetime.now().
        aware = timestamp.astimezone(timezone.utc)
        age = timestamp_age_seconds(timestamp)
        if (
            what == "account risk state"
            and aware.date() != datetime.now(timezone.utc).date()
        ):
            raise ExecutionUnavailable("Account risk state belongs to another UTC day")
        if is_stale(age, self._max_age):
            raise ExecutionUnavailable(f"Stale or future {what}")

    def _validate_order(self, account, order):
        try:
            validate_order_terms(account, order)
        except InvalidOrderTerms as exc:
            raise ExecutionRejected(str(exc)) from exc

    async def _state(self, broker, account):
        try:
            state = await asyncio.wait_for(
                broker.account.get_risk_state(account), self._timeout
            )
        except Exception as exc:
            raise ExecutionUnavailable(
                "Authoritative account risk state unavailable"
            ) from exc
        if (
            not isinstance(state, AccountRiskState)
            or not state.complete
            or not state.source
        ):
            raise ExecutionUnavailable("Incomplete account risk state")
        self._fresh(state.observed_at, "account risk state")
        ctx = state.context
        if ctx.balance.account_id != account:
            raise ExecutionUnavailable("Risk state account mismatch")
        for key in ("net_liquidation", "buying_power", "cash", "maintenance_margin"):
            _decimal(getattr(ctx.balance, key), key, positive=False)
        if ctx.balance.net_liquidation <= 0:
            raise ExecutionRejected("Account equity must be positive")
        if ctx.daily_pnl is None or ctx.daily_trade_count is None:
            raise ExecutionUnavailable(
                "Measured daily PnL and trade count are required"
            )
        _decimal(ctx.daily_pnl, "daily PnL", positive=False)
        if type(ctx.daily_trade_count) is not int or ctx.daily_trade_count < 0:
            raise ExecutionUnavailable("Invalid daily trade count")
        for pos in ctx.positions:
            for key in (
                "quantity",
                "market_value",
                "avg_cost",
                "unrealized_pnl",
                "realized_pnl",
            ):
                _decimal(getattr(pos, key), key, positive=False)
        return deepcopy(state)

    async def _quote(self, broker, order):
        try:
            quote = await asyncio.wait_for(
                broker.market_data.get_quote(order.symbol), self._timeout
            )
        except Exception as exc:
            raise ExecutionUnavailable("Execution quote unavailable") from exc
        if not isinstance(quote, Quote) or quote.symbol != order.symbol:
            raise ExecutionUnavailable("Execution quote symbol mismatch")
        self._fresh(quote.timestamp, "quote")
        prices = [
            _decimal(p, "quote price")
            for p in (quote.last, quote.ask, quote.bid)
            if p is not None
        ]
        if not prices:
            raise ExecutionUnavailable("Execution quote has no usable price")
        prices += [
            getattr(order, name)
            for name in ("limit_price", "stop_price")
            if hasattr(order, name)
        ]
        if not prices:
            raise ExecutionUnavailable("Execution quote has no usable price")
        # Rules consume last: use the conservative price including limit/trigger.
        if (
            order.symbol.asset_type == AssetType.FUTURE
            and order.symbol.multiplier is None
        ):
            raise ExecutionRejected("Futures require an explicit contract multiplier")
        multiplier = (
            order.symbol.multiplier
            if order.symbol.multiplier is not None
            else (100 if order.symbol.asset_type == AssetType.OPTION else 1)
        )
        price = max(prices) * _decimal(multiplier, "contract multiplier")
        if isinstance(order, TrailingStopOrder) and order.side == OrderSide.BUY:
            price += (
                order.trail_amount * multiplier
                if order.trail_amount is not None
                else price * order.trail_percent / 100
            )
        return replace(quote, last=price)

    async def _journal(self):
        raw = await self._store.get(_JOURNAL)
        try:
            data = json.loads(raw) if raw else []
            if not isinstance(data, list):
                raise ValueError("not a list")
            return data
        except Exception as exc:
            raise ExecutionUnavailable(
                "Execution reservation journal is invalid"
            ) from exc

    async def _prepare(
        self, broker, account, order, journal, *, exclude=None, state_override=None
    ):
        self._validate_order(account, order)
        if not self._risk.rules:
            raise ExecutionUnavailable("Execution risk policy has no rules")
        state = state_override or await self._state(broker, account)
        if state.symbol_identity == "ticker_asset" and order.symbol != Symbol(
            order.symbol.ticker, order.symbol.asset_type
        ):
            raise ExecutionRejected(
                "Paper ledger cannot represent this symbol's exchange, currency or derivative identity"
            )
        name = self._broker_name(broker)
        journal[:] = [
            r
            for r in journal
            if not (
                r["broker"] == name
                and r["account"] == account
                and (
                    r["id"] in state.terminal_order_ids
                    or (state.epoch and r.get("epoch") and r["epoch"] != state.epoch)
                )
            )
        ]
        pending = {r.order_id: r for r in state.orders if r.status in _OPEN}
        for r in journal:
            if (
                r["broker"] == name
                and r["account"] == account
                and r["id"] not in pending
            ):
                pending[r["id"]] = OrderSnapshot(
                    r["id"], decode_order(r["order"]), OrderStatus.SUBMITTED
                )
        ctx = state.context
        counted = next((o for o in state.orders if o.order_id == exclude), None)
        if counted is not None and counted.submitted_at is not None:
            if (
                counted.submitted_at.astimezone(timezone.utc).date()
                == datetime.now(timezone.utc).date()
            ):
                ctx.daily_trade_count = max(0, ctx.daily_trade_count - 1)
        exposure_quotes = []
        state.exposure_observed_at = None
        if any(rule.name == "max_portfolio_exposure" for rule in self._risk.rules):
            ctx.exposure_positions = deepcopy(ctx.positions)
            ctx.pending_exposure = []
            ctx.exposure_prices = {}
            # Reprice every held/open symbol. Other risk rules still consume their
            # existing quantity reservations; dollar exposure never reads those
            # synthetic zero-value positions.
            for position in ctx.exposure_positions:
                if position.quantity:
                    held_order = MarketOrder(
                        position.symbol, OrderSide.BUY, abs(position.quantity), account
                    )
                    held_quote = await self._quote(broker, held_order)
                    exposure_quotes.append(held_quote)
                    ctx.exposure_prices[position.symbol] = held_quote.last
            for oid, snapshot in pending.items():
                if oid == exclude:
                    continue
                outstanding = deepcopy(snapshot.order)
                self._validate_order(account, outstanding)
                filled = _decimal(
                    snapshot.filled_quantity, "filled quantity", positive=False
                )
                if filled < 0 or filled > outstanding.quantity:
                    raise ExecutionUnavailable("Invalid outstanding order quantity")
                remaining = outstanding.quantity - filled
                if remaining <= 0:
                    continue
                pending_quote = await self._quote(broker, outstanding)
                exposure_quotes.append(pending_quote)
                ctx.exposure_prices[outstanding.symbol] = max(
                    ctx.exposure_prices.get(outstanding.symbol, Decimal(0)),
                    pending_quote.last,
                )
                ctx.pending_exposure.append((outstanding, remaining))
        held_quantities = {}
        for position in ctx.positions:
            held_quantities[position.symbol] = (
                held_quantities.get(position.symbol, Decimal(0)) + position.quantity
            )
        # Reserve only same-direction pending quantities for this symbol. Opposite
        # orders must not manufacture capacity by netting unfilled exposure.
        for oid, snap in pending.items():
            self._validate_order(account, snap.order)
            filled = _decimal(snap.filled_quantity, "filled quantity", positive=False)
            if filled < 0 or filled > snap.order.quantity:
                raise ExecutionUnavailable("Invalid outstanding order quantity")
            if oid == exclude:
                continue
            remaining = snap.order.quantity - filled
            if remaining <= 0:
                continue
            if snap.order.symbol != order.symbol or snap.order.side == order.side:
                signed = remaining if snap.order.side == OrderSide.BUY else -remaining
                if snap.order.symbol != order.symbol:
                    # Other symbols reserve occupied slots, not hypothetical net
                    # positions. Pending exits cannot free a held slot, and opposing
                    # entries on a flat symbol must reserve a slot together.
                    held = held_quantities.get(snap.order.symbol, Decimal(0))
                    signed = -remaining if held < 0 else remaining
                ctx.positions.append(
                    Position(
                        snap.order.symbol,
                        signed,
                        Decimal(0),
                        Decimal(0),
                        Decimal(0),
                        Decimal(0),
                    )
                )
            # Providers count accepted orders. Unacknowledged reservations add to
            # count until the provider reports the accepted order in its snapshot.
            if oid not in {o.order_id for o in state.orders}:
                ctx.daily_trade_count += 1
        rule_names = {r.name for r in self._risk.rules}
        if "sector_concentration" in rule_names and not ctx.sectors:
            raise ExecutionUnavailable("Measured sector exposure is required")
        symbols = {p.symbol.ticker for p in ctx.positions if p.quantity != 0} | {
            order.symbol.ticker
        }
        if "max_correlation" in rule_names and len(symbols) > 1:
            if any(len(ctx.price_histories.get(symbol, [])) < 2 for symbol in symbols):
                raise ExecutionUnavailable(
                    "Price histories for correlation risk are required"
                )
        quote = await self._quote(broker, order)
        requested_quantity = order.quantity
        result = await self._risk.evaluate_order(order, quote, ctx)
        if not result.passed:
            raise ExecutionRejected(f"{result.rule_name}: {result.reason}")
        if result.adjusted_quantity is not None:
            quantity = _decimal(result.adjusted_quantity, "risk-adjusted quantity")
            if quantity > requested_quantity:
                raise ExecutionRejected("Risk adjustment cannot increase quantity")
            order.quantity = quantity
        if order.quantity > requested_quantity:
            raise ExecutionRejected("Risk adjustment cannot increase quantity")
        self._validate_order(account, order)
        self._fresh(state.observed_at, "account risk state")
        self._fresh(quote.timestamp, "quote")
        for exposure_quote in exposure_quotes:
            self._fresh(exposure_quote.timestamp, "portfolio exposure quote")
        if exposure_quotes:
            state.exposure_observed_at = min(q.timestamp for q in exposure_quotes)
        return state, quote

    async def _save_result(
        self, journal, name, account, order, result, *, replaced=None, epoch=""
    ):
        if (
            isinstance(result, OrderResult)
            and result.status == OrderStatus.REJECTED
            and result.filled_quantity == 0
        ):
            return result
        if not isinstance(result, OrderResult) or not result.order_id:
            raise ExecutionUnavailable("Broker returned no authoritative order receipt")
        if result.status not in set(OrderStatus):
            raise ExecutionUnavailable("Broker returned unknown order status")
        filled = _decimal(
            result.filled_quantity, "receipt filled quantity", positive=False
        )
        if (
            filled < 0
            or filled > order.quantity
            or (result.status == OrderStatus.FILLED and filled != order.quantity)
        ):
            raise ExecutionUnavailable("Broker returned inconsistent fill receipt")
        if replaced:
            journal[:] = [
                r
                for r in journal
                if not (
                    r["broker"] == name
                    and r["account"] == account
                    and r["id"] == replaced
                )
            ]
        # Filled orders also reserve until a fresh provider snapshot observes them.
        if result.status in (_OPEN | {OrderStatus.FILLED}):
            journal.append(
                {
                    "broker": name,
                    "account": account,
                    "id": result.order_id,
                    "order": encode_order(order),
                    "epoch": epoch,
                }
            )
        return result

    async def _record_attempt(
        self, receipt, name, account, order, operation, order_id=None, epoch=""
    ):
        receipt["attempt"] = {
            "token": receipt["token"],
            "dispatch_id": receipt["token"],
            "epoch": epoch,
            "broker": name,
            "account": account,
            "operation": operation,
            "order_id": order_id,
            "order": encode_order(order),
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "status": "prepared",
        }
        receipt["raw_attempt"] = json.dumps(receipt["attempt"], default=str)
        await self._store.set(_ATTEMPT, receipt["raw_attempt"])

    async def _acknowledge_attempt(self, receipt, result):
        receipt["attempt"].update(
            status="acknowledged",
            result_order_id=result.order_id,
            result_status=result.status.value,
        )
        applied = await self._store.eval(
            """-- execution:finalize
            if redis.call('GET', KEYS[1]) ~= ARGV[1] or
               redis.call('GET', KEYS[2]) ~= ARGV[2] then return 0 end
            redis.call('SET', KEYS[3], ARGV[3])
            redis.call('SET', KEYS[2], ARGV[4])
            return 1
            """,
            3,
            _LOCK,
            _ATTEMPT,
            _JOURNAL,
            receipt["token"],
            receipt["raw_attempt"],
            json.dumps(receipt["journal"], default=str),
            json.dumps(receipt["attempt"], default=str),
        )
        if applied != 1:
            raise ExecutionUnavailable(
                "Dispatch ownership changed; reconciliation required",
                outcome_unknown=True,
            )

    async def reconciliation_status(self):
        """Read-only diagnostics. Never clears an uncertain write automatically."""
        return {
            "lock": await self._store.get(_LOCK),
            "attempt": json.loads(await self._store.get(_ATTEMPT) or "null"),
            "reservations": await self._journal(),
        }

    async def recover_acknowledged(self, token: str):
        """Recover a persisted receipt, never infer success from matching terms.

        Trading must remain halted. A receipt without an order identity or a
        prepared-only attempt still needs venue reconciliation and stays locked.
        Redis atomically records recovery and releases only the matching lock.
        """
        async with self._local_lock:
            await self._risk.sync_halt()
            if not self._risk.check_kill_active():
                raise ExecutionRejected("Halt trading before recovery")
            raw = await self._store.get(_ATTEMPT)
            attempt = json.loads(raw or "null")
            if not attempt or attempt.get("token") != token:
                raise ExecutionRejected("Recovery token does not match attempt")
            if attempt.get("status") != "acknowledged":
                raise ExecutionRejected(
                    "Outcome has no durable receipt; venue reconciliation required"
                )
            broker = self._brokers.get(attempt["broker"])
            if broker is None:
                raise ExecutionUnavailable("Recovery broker is unavailable")
            state = await self._state(broker, attempt["account"])
            order_id = attempt.get("result_order_id")
            # Initially support terminal receipts only. Open/partial outcomes
            # require explicit reservation reconstruction, never blind unlocking.
            if not order_id or order_id not in state.terminal_order_ids:
                raise ExecutionRejected("Receipt is not authoritatively terminal")
            if attempt.get("result_status") not in {
                OrderStatus.FILLED.value,
                OrderStatus.CANCELLED.value,
                OrderStatus.REJECTED.value,
            }:
                raise ExecutionRejected("Receipt requires open-order reconciliation")
            journal_raw = await self._store.get(_JOURNAL)
            journal = json.loads(journal_raw or "[]")
            if not isinstance(journal, list):
                raise ExecutionUnavailable("Invalid reservation journal")
            journal = [
                r
                for r in journal
                if not (
                    r["broker"] == attempt["broker"]
                    and r["account"] == attempt["account"]
                    and r["id"] == order_id
                )
            ]
            recovered = dict(
                attempt,
                status="recovered",
                recovered_at=datetime.now(timezone.utc).isoformat(),
            )
            # Compare all inputs as well as persisted halt: another recovery,
            # resume, or changed journal must invalidate this proposal.
            applied = await self._store.eval(
                """
                if redis.call('GET', KEYS[1]) ~= ARGV[1] or
                   redis.call('GET', KEYS[2]) ~= ARGV[2] or
                   (redis.call('GET', KEYS[3]) or '') ~= ARGV[3] or
                   redis.call('GET', KEYS[4]) ~= 'true' then return 0 end
                redis.call('SET', KEYS[3], ARGV[4])
                redis.call('SET', KEYS[2], ARGV[5])
                redis.call('DEL', KEYS[1])
                return 1
                """,
                4,
                _LOCK,
                _ATTEMPT,
                _JOURNAL,
                "kill_switch:active",
                token,
                raw,
                journal_raw or "",
                json.dumps(journal, default=str),
                json.dumps(recovered, default=str),
            )
            if applied != 1:
                raise ExecutionRejected(
                    "Recovery state changed; admission remains blocked"
                )
            return recovered

    async def _dispatch_submit(self, broker, account, order, dispatch_id, epoch):
        if callable(getattr(type(broker.orders), "submit_dispatch", None)):
            return await broker.orders.submit_dispatch(
                account, order, dispatch_id, epoch
            )
        return await broker.orders.place_order(account, order)

    async def _dispatch_amend(self, broker, order_id, changes, dispatch_id, epoch):
        if callable(getattr(type(broker.orders), "amend_dispatch", None)):
            return await broker.orders.amend_dispatch(
                order_id, changes, dispatch_id, epoch
            )
        return await broker.orders.modify_order(order_id, changes)

    async def recover(self, token: str):
        """Reconcile an exact dispatch, preserving open exposure before unlocking.

        This never sends an order. Providers may fence a not-yet-applied dispatch
        to establish conclusive absence. Quiesce workers and halt before recovery.
        """
        from execution.dispatch import DispatchEvidence

        async with self._local_lock:
            await self._risk.sync_halt()
            if not self._risk.check_kill_active():
                raise ExecutionRejected("Halt trading before recovery")
            raw = await self._store.get(_ATTEMPT)
            attempt = json.loads(raw or "null")
            if not attempt or attempt.get("token") != token:
                raise ExecutionRejected("Recovery token does not match attempt")
            lock = await self._store.get(_LOCK)
            if lock not in (token, token.encode()):
                raise ExecutionRejected("Recovery lock no longer matches")
            if attempt.get("dispatch_id") != token:
                raise ExecutionRejected(
                    "Legacy attempt has no durable dispatch identity"
                )
            broker = self._brokers.get(attempt["broker"])
            if broker is None:
                raise ExecutionUnavailable("Recovery broker is unavailable")
            journal_raw = await self._store.get(_JOURNAL)
            journal = json.loads(journal_raw or "[]")
            if not isinstance(journal, list):
                raise ExecutionUnavailable("Invalid reservation journal")
            try:
                evidence = await asyncio.wait_for(
                    broker.orders.reconcile_dispatch(deepcopy(attempt)), self._timeout
                )
            except Exception as exc:
                raise ExecutionUnavailable(
                    "Dispatch reconciliation unavailable"
                ) from exc
            if not isinstance(evidence, DispatchEvidence) or evidence.final is not True:
                raise ExecutionRejected("Dispatch outcome remains uncertain")
            order = decode_order(attempt["order"])
            if (
                evidence.dispatch_id != token
                or evidence.account_id != attempt["account"]
                or evidence.operation != attempt["operation"]
                or evidence.original_order_id != attempt.get("order_id")
                or evidence.epoch != attempt.get("epoch", "")
                or encode_order(evidence.order) != encode_order(order)
            ):
                raise ExecutionRejected("Dispatch evidence identity mismatch")
            self._fresh(evidence.observed_at, "dispatch evidence")
            state = await self._state(broker, attempt["account"])
            if state.epoch != evidence.epoch:
                raise ExecutionRejected(
                    "Account generation changed; reconcile manually"
                )
            snap = evidence.snapshot
            if evidence.outcome not in {"applied", "not_accepted"}:
                raise ExecutionRejected("Unknown dispatch outcome")
            if evidence.outcome == "not_accepted":
                if snap is not None:
                    raise ExecutionRejected("Contradictory rejected dispatch evidence")
                # A failed amendment leaves its original reservation in place.
                result_id = None
            else:
                if not isinstance(snap, OrderSnapshot) or not snap.order_id:
                    raise ExecutionRejected("Missing authoritative order snapshot")
                if encode_order(snap.order) != encode_order(order):
                    raise ExecutionRejected("Reconciled order terms differ")
                filled = _decimal(
                    snap.filled_quantity, "reconciled fill", positive=False
                )
                if filled < 0 or filled > order.quantity:
                    raise ExecutionRejected("Invalid reconciled fill")
                if snap.status == OrderStatus.FILLED and filled != order.quantity:
                    raise ExecutionRejected("Incomplete filled receipt")
                if snap.status == OrderStatus.REJECTED and filled != 0:
                    raise ExecutionRejected("Rejected order has fills")
                if snap.status in _OPEN:
                    current = next(
                        (o for o in state.orders if o.order_id == snap.order_id), None
                    )
                    if (
                        current is None
                        or current.status != snap.status
                        or current.filled_quantity != filled
                        or encode_order(current.order) != encode_order(order)
                    ):
                        raise ExecutionRejected(
                            "Open order does not match account snapshot"
                        )
                elif (
                    snap.status
                    not in {
                        OrderStatus.FILLED,
                        OrderStatus.CANCELLED,
                        OrderStatus.REJECTED,
                    }
                    or snap.order_id not in state.terminal_order_ids
                ):
                    raise ExecutionRejected("Order is not authoritatively terminal")
                result_id = snap.order_id
                remove_ids = {result_id}
                if attempt["operation"] == "amend":
                    remove_ids.add(attempt["order_id"])
                journal = [
                    r
                    for r in journal
                    if not (
                        r["broker"] == attempt["broker"]
                        and r["account"] == attempt["account"]
                        and r["id"] in remove_ids
                    )
                ]
                if snap.status in _OPEN:
                    journal.append(
                        {
                            "broker": attempt["broker"],
                            "account": attempt["account"],
                            "id": result_id,
                            "order": encode_order(order),
                            "epoch": state.epoch,
                            "dispatch_id": token,
                        }
                    )
            self._fresh(evidence.observed_at, "dispatch evidence")
            self._fresh(state.observed_at, "account risk state")
            recovered = dict(
                attempt,
                status="recovered",
                recovery_outcome=evidence.outcome,
                result_order_id=result_id,
                recovered_at=datetime.now(timezone.utc).isoformat(),
            )
            applied = await self._store.eval(
                """
                if redis.call('GET', KEYS[1]) ~= ARGV[1] or
                   redis.call('GET', KEYS[2]) ~= ARGV[2] or
                   (redis.call('GET', KEYS[3]) or '') ~= ARGV[3] or
                   redis.call('GET', KEYS[4]) ~= 'true' then return 0 end
                redis.call('SET', KEYS[3], ARGV[4])
                redis.call('SET', KEYS[2], ARGV[5])
                redis.call('DEL', KEYS[1])
                return 1
                """,
                4,
                _LOCK,
                _ATTEMPT,
                _JOURNAL,
                "kill_switch:active",
                token,
                raw,
                journal_raw or "",
                json.dumps(journal, default=str),
                json.dumps(recovered, default=str),
            )
            if applied != 1:
                raise ExecutionRejected(
                    "Recovery state changed; admission remains blocked"
                )
            return recovered

    async def preview(self, broker, account, order):
        """Advisory result for shadow/decision logging; submit always checks again."""
        from risk.rules import RiskResult

        try:
            candidate = deepcopy(order)
            self._broker_name(broker)
            async with self._admission():
                await self._prepare(broker, account, candidate, await self._journal())
            return RiskResult(passed=True, adjusted_quantity=candidate.quantity)
        except Exception as exc:
            return RiskResult(passed=False, rule_name="execution", reason=str(exc))

    async def submit(self, broker, account, order):
        order = deepcopy(order)
        name = self._broker_name(broker)
        async with self._admission() as receipt:
            journal = await self._journal()
            receipt["journal"] = journal
            state, quote = await self._prepare(broker, account, order, journal)
            await self._record_attempt(
                receipt, name, account, order, "submit", epoch=state.epoch
            )
            self._fresh(state.observed_at, "account risk state")
            self._fresh(quote.timestamp, "quote")
            if state.exposure_observed_at is not None:
                self._fresh(state.exposure_observed_at, "portfolio exposure quote")
            async with self._risk.dispatch_guard():
                self._fresh(state.observed_at, "account risk state")
                self._fresh(quote.timestamp, "quote")
                if state.exposure_observed_at is not None:
                    self._fresh(state.exposure_observed_at, "portfolio exposure quote")
                receipt["uncertain"] = True
                result = await asyncio.wait_for(
                    self._dispatch_submit(
                        broker, account, order, receipt["token"], state.epoch
                    ),
                    self._timeout,
                )
                await self._save_result(
                    journal, name, account, order, result, epoch=state.epoch
                )
                await self._acknowledge_attempt(receipt, result)
                receipt["uncertain"] = False
                return result

    async def amend(self, broker, order_id, changes):
        name = self._broker_name(broker)
        if not changes or set(changes) - {"quantity", "limit_price", "stop_price"}:
            raise ExecutionRejected("Unsupported amendment fields")
        async with self._admission() as receipt:
            journal = await self._journal()
            receipt["journal"] = journal
            original = next(
                (r for r in journal if r["broker"] == name and r["id"] == order_id),
                None,
            )
            if original is None:
                raise ExecutionRejected(
                    "Unknown order; authoritative original order is required"
                )
            account = original["account"]
            state = await self._state(broker, account)
            current = next(
                (
                    s
                    for s in state.orders
                    if s.order_id == order_id and s.status in _OPEN
                ),
                None,
            )
            if current is None:
                raise ExecutionRejected("Order is not authoritatively amendable")
            order = deepcopy(current.order)
            if encode_order(order) != encode_order(decode_order(original["order"])):
                raise ExecutionUnavailable(
                    "Order changed outside execution boundary; reconcile first"
                )
            for key, value in changes.items():
                if not hasattr(order, key):
                    raise ExecutionRejected(f"{key} is not valid for this order type")
                setattr(order, key, _decimal(value, key))
            if order.quantity <= current.filled_quantity:
                raise ExecutionRejected(
                    "Amended quantity must exceed already filled quantity"
                )
            full_quantity = order.quantity
            # Positions already contain filled shares. Evaluate remaining exposure.
            order.quantity -= current.filled_quantity
            _, quote = await self._prepare(
                broker, account, order, journal, exclude=order_id, state_override=state
            )
            approved_remaining = order.quantity
            order.quantity += current.filled_quantity
            canonical = {key: getattr(order, key) for key in changes}
            if order.quantity != full_quantity:
                canonical["quantity"] = order.quantity
            if approved_remaining <= 0:
                raise ExecutionRejected("Amendment has no approved remaining quantity")
            await self._record_attempt(
                receipt, name, account, order, "amend", order_id, epoch=state.epoch
            )
            self._fresh(state.observed_at, "account risk state")
            self._fresh(quote.timestamp, "quote")
            if state.exposure_observed_at is not None:
                self._fresh(state.exposure_observed_at, "portfolio exposure quote")
            async with self._risk.dispatch_guard():
                self._fresh(state.observed_at, "account risk state")
                self._fresh(quote.timestamp, "quote")
                if state.exposure_observed_at is not None:
                    self._fresh(state.exposure_observed_at, "portfolio exposure quote")
                receipt["uncertain"] = True
                result = await asyncio.wait_for(
                    self._dispatch_amend(
                        broker, order_id, canonical, receipt["token"], state.epoch
                    ),
                    self._timeout,
                )
                if (
                    isinstance(result, OrderResult)
                    and result.status == OrderStatus.REJECTED
                    and result.filled_quantity == 0
                ):
                    # Original order may remain active after rejected amendment.
                    await self._acknowledge_attempt(receipt, result)
                    receipt["uncertain"] = False
                    return result
                await self._save_result(
                    journal,
                    name,
                    account,
                    order,
                    result,
                    replaced=order_id,
                    epoch=state.epoch,
                )
                await self._acknowledge_attempt(receipt, result)
                receipt["uncertain"] = False
                return result
