import json
from datetime import datetime, timezone, timedelta
from dataclasses import replace
import uuid
from decimal import Decimal
from broker.models import (
    AccountBalance,
    Position,
    Symbol,
    AssetType,
    OrderResult,
    OrderStatus,
    OrderSide,
    is_stale,
    timestamp_age_seconds,
)
from broker.order_terms import decode_order, encode_order, order_payload

import aiosqlite
from storage.postgres import PostgresDB
from storage.unit_of_work import UnitOfWork
from storage.inspection import CheckIssue, inspect_tables


class PaperStore:
    def __init__(self, db=None, *, unit_of_work: UnitOfWork | None = None):
        if db is not None and unit_of_work is not None:
            raise ValueError("Pass a database or a unit of work, not both")
        self._uow = unit_of_work or UnitOfWork(db)
        self._is_postgres = self._uow.is_postgres

    @property
    def _db(self):
        return self._uow._db

    async def _get_db(self):
        return await self._uow.handle()

    async def close(self) -> None:
        await self._uow.close()

    def transaction(self):
        """One owned transaction; never commit/rollback another caller's work."""
        return self._uow.transaction()

    async def ensure_account(self, account_id: str, initial_balance) -> None:
        async with self.transaction() as db:
            existing = await (
                await db.execute(
                    "SELECT account_id FROM paper_accounts WHERE account_id=?",
                    (account_id,),
                )
            ).fetchone()
            if existing:
                await self.initialize_risk_coverage(account_id, fresh=False)
                return
            value = float(initial_balance)
            await db.execute(
                "INSERT INTO paper_accounts (account_id, net_liquidation, buying_power, cash, maintenance_margin) VALUES (?, ?, ?, ?, 0)",
                (account_id, value, value, value),
            )
            await self.initialize_risk_coverage(account_id, fresh=True)

    async def supports_transactions(self) -> bool:
        return await self._uow.supports_transactions()

    async def check_storage(self) -> tuple[CheckIssue, ...]:
        """Inspect this ledger's eager schema without initializing or writing it."""
        if self._uow._db is None or self._uow._closed:
            return (CheckIssue("paper_store", "Unavailable"),)
        if not await self.supports_transactions():
            return (CheckIssue("paper_store", "UnsupportedTransactions"),)
        return await inspect_tables(
            await self._get_db(),
            {
                "paper_order_terms": "order_id account_id order_payload submitted_at epoch triggered",
                "paper_fill_events": "fill_id order_id account_id quantity price commission occurred_at",
                "paper_match_ticks": "tick_id payload",
                "paper_dispatches": "dispatch_id account_id order_payload epoch result_payload operation original_order_id",
                "paper_risk_coverage": "account_id complete_from generation",
                "paper_risk_events": "event_id account_id order_id kind net_pnl occurred_at",
                "paper_accounts": "account_id net_liquidation buying_power cash maintenance_margin",
                "paper_positions": "account_id symbol asset_type quantity avg_cost realized_pnl resolved_at",
                "paper_orders": "order_id account_id symbol side quantity status filled_quantity avg_fill_price created_at",
            },
        )

    async def account_generation(self, account_id: str) -> str | None:
        """The account's current generation, or None if it has no coverage row."""
        db = await self._get_db()
        row = await (
            await db.execute(
                "SELECT generation FROM paper_risk_coverage WHERE account_id=?",
                (account_id,),
            )
        ).fetchone()
        return row["generation"] if row else None

    async def reset_account(self, account_id: str, initial_balance) -> None:
        """Clear the account's ledger and start a new generation.

        Dispatch records and applied ticks are kept: they fence late deliveries
        and replays from the previous generation.
        """
        async with self.transaction() as db:
            for table in (
                "paper_positions",
                "paper_orders",
                "paper_order_terms",
                "paper_fill_events",
                "paper_risk_events",
                "paper_risk_coverage",
            ):
                await db.execute(
                    f"DELETE FROM {table} WHERE account_id = ?", (account_id,)
                )
            initial = float(initial_balance)
            await db.execute(
                """
                INSERT OR REPLACE INTO paper_accounts
                    (account_id, net_liquidation, buying_power, cash, maintenance_margin)
                VALUES (?, ?, ?, ?, 0.0)
                """,
                (account_id, initial, initial, initial),
            )
            await self.initialize_risk_coverage(account_id, fresh=True)

    async def debit_cash(self, account_id: str, amount: Decimal) -> None:
        db = await self._get_db()
        await db.execute(
            "UPDATE paper_accounts SET cash = cash - ? WHERE account_id = ?",
            (float(amount), account_id),
        )

    async def open_order_ids(self, account_id: str) -> list[str]:
        db = await self._get_db()
        rows = await (
            await db.execute(
                "SELECT order_id FROM paper_orders WHERE account_id=? AND status IN (?, ?)",
                (account_id, OrderStatus.SUBMITTED.value, OrderStatus.PARTIAL.value),
            )
        ).fetchall()
        return [row["order_id"] for row in rows]

    async def open_orders_by_arrival(self, account_id: str) -> list[tuple[str, bool]]:
        """Open order ids in arrival order, each with its stop-triggered flag."""
        db = await self._get_db()
        rows = await (
            await db.execute(
                "SELECT t.order_id, t.triggered FROM paper_order_terms t JOIN paper_orders o ON o.order_id=t.order_id WHERE t.account_id=? AND o.status IN (?, ?) ORDER BY t.submitted_at, t.order_id",
                (account_id, OrderStatus.SUBMITTED.value, OrderStatus.PARTIAL.value),
            )
        ).fetchall()
        return [(row["order_id"], bool(row["triggered"])) for row in rows]

    async def set_stop_triggered(self, order_id: str, triggered: bool) -> None:
        db = await self._get_db()
        await db.execute(
            "UPDATE paper_order_terms SET triggered=? WHERE order_id=?",
            (1 if triggered else 0, order_id),
        )

    async def fill_evidence(self, order_id: str):
        """Recorded fills for an order: rows of quantity, price, commission."""
        db = await self._get_db()
        return await (
            await db.execute(
                "SELECT quantity, price, commission FROM paper_fill_events WHERE order_id=?",
                (order_id,),
            )
        ).fetchall()

    async def order_terms_for_account(self, account_id: str):
        """Rows of order_id, order_payload for every order the account has."""
        db = await self._get_db()
        return await (
            await db.execute(
                "SELECT order_id,order_payload FROM paper_order_terms WHERE account_id=?",
                (account_id,),
            )
        ).fetchall()

    async def get_dispatch(self, dispatch_id: str):
        db = await self._get_db()
        return await (
            await db.execute(
                "SELECT * FROM paper_dispatches WHERE dispatch_id=?", (dispatch_id,)
            )
        ).fetchone()

    async def insert_dispatch(
        self,
        dispatch_id: str,
        account_id: str,
        payload: str,
        generation: str,
        result_payload: str,
        operation: str = "submit",
        original_order_id: str | None = None,
    ) -> None:
        db = await self._get_db()
        await db.execute(
            "INSERT INTO paper_dispatches (dispatch_id, account_id, order_payload, epoch, result_payload, operation, original_order_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                dispatch_id,
                account_id,
                payload,
                generation,
                result_payload,
                operation,
                original_order_id,
            ),
        )

    async def submit_receipts(self, account_id: str, generation: str | None = None):
        """Submit dispatch records for an account: order_payload, result_payload."""
        db = await self._get_db()
        if generation is None:
            cursor = await db.execute(
                "SELECT order_payload,result_payload FROM paper_dispatches WHERE account_id=? AND operation='submit'",
                (account_id,),
            )
        else:
            cursor = await db.execute(
                "SELECT order_payload,result_payload FROM paper_dispatches WHERE account_id=? AND epoch=? AND operation='submit'",
                (account_id, generation),
            )
        return await cursor.fetchall()

    async def init_tables(self, *, initial_balance=100000.0) -> None:
        """Initialize the ledger and seed a missing default account only.

        Existing balances and risk coverage are preserved. Callers without an
        explicit starting balance retain the historical standalone default.
        """
        db = await self._get_db()
        if isinstance(db, PostgresDB):
            async with self.transaction():
                await self._init_tables(initial_balance)
        else:
            await self._init_tables(initial_balance)

    async def _init_tables(self, initial_balance) -> None:
        db = await self._get_db()
        adopted = await self._uow.adopt_dedicated_connection(db, busy_timeout=True)
        if adopted is not None:
            db = adopted
        elif (
            isinstance(db, aiosqlite.Connection)
            and not self._uow.owns_connection
            and db.in_transaction
        ):
            raise RuntimeError("Paper connection already has an unrelated transaction")
        ts_default = "NOW()" if self._is_postgres else "(datetime('now'))"
        for sql in [
            """CREATE TABLE IF NOT EXISTS paper_order_terms (
                order_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                order_payload TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                epoch TEXT NOT NULL,
                triggered INTEGER NOT NULL DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS paper_fill_events (
                fill_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                quantity TEXT NOT NULL,
                price TEXT NOT NULL,
                commission TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS paper_match_ticks (
                tick_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS paper_dispatches (
                dispatch_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                order_payload TEXT NOT NULL,
                epoch TEXT NOT NULL,
                result_payload TEXT NOT NULL,
                operation TEXT NOT NULL DEFAULT 'submit',
                original_order_id TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS paper_risk_coverage (
                account_id TEXT PRIMARY KEY,
                complete_from TEXT NOT NULL,
                generation TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS paper_risk_events (
                event_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                order_id TEXT,
                kind TEXT NOT NULL,
                net_pnl TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS paper_accounts (
                account_id TEXT PRIMARY KEY,
                net_liquidation REAL NOT NULL,
                buying_power REAL NOT NULL,
                cash REAL NOT NULL,
                maintenance_margin REAL NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS paper_positions (
                account_id TEXT,
                symbol TEXT,
                asset_type TEXT,
                quantity REAL NOT NULL,
                avg_cost REAL NOT NULL,
                realized_pnl REAL NOT NULL DEFAULT 0.0,
                resolved_at TEXT,
                PRIMARY KEY (account_id, symbol, asset_type)
            )""",
            f"""CREATE TABLE IF NOT EXISTS paper_orders (
                order_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                status TEXT NOT NULL,
                filled_quantity REAL NOT NULL,
                avg_fill_price REAL,
                created_at TEXT NOT NULL DEFAULT {ts_default}
            )""",
        ]:
            await db.execute(
                sql.replace(" REAL", " DOUBLE PRECISION") if self._is_postgres else sql
            )

        # PostgreSQL REAL is float32, unlike SQLite REAL (float64). Preserve
        # fractional quantities and cash with the same precision on both stores.
        if self._is_postgres:
            for table, columns in {
                "paper_accounts": (
                    "net_liquidation",
                    "buying_power",
                    "cash",
                    "maintenance_margin",
                ),
                "paper_positions": ("quantity", "avg_cost", "realized_pnl"),
                "paper_orders": ("quantity", "filled_quantity", "avg_fill_price"),
            }.items():
                for column in columns:
                    await db.execute(
                        f"ALTER TABLE {table} ALTER COLUMN {column} TYPE DOUBLE PRECISION"
                    )

        dispatch_additions = {
            "operation": "TEXT NOT NULL DEFAULT 'submit'",
            "original_order_id": "TEXT",
        }
        if self._is_postgres:
            for name, definition in dispatch_additions.items():
                await db.execute(
                    f"ALTER TABLE paper_dispatches ADD COLUMN IF NOT EXISTS {name} {definition}"
                )
        else:
            columns = {
                row[1]
                for row in await (
                    await db.execute("PRAGMA table_info(paper_dispatches)")
                ).fetchall()
            }
            for name, definition in dispatch_additions.items():
                if name not in columns:
                    await db.execute(
                        f"ALTER TABLE paper_dispatches ADD COLUMN {name} {definition}"
                    )

        # Migrate: add resolved_at column if not present (idempotent ALTER TABLE)
        try:
            await db.execute(
                "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS resolved_at TEXT"
                if self._is_postgres
                else "ALTER TABLE paper_positions ADD COLUMN resolved_at TEXT"
            )
            await db.commit()
        except Exception as exc:
            _msg = str(exc).lower()
            if "duplicate column name" not in _msg and "already exists" not in _msg:
                raise

        # Existing accounts cannot claim complete risk evidence on migration day.
        existing_accounts = await (
            await db.execute("SELECT account_id FROM paper_accounts")
        ).fetchall()
        for existing in existing_accounts:
            await self.initialize_risk_coverage(existing["account_id"], fresh=False)

        # Ensure default paper account exists
        initial = float(initial_balance)
        await db.execute(
            """
            INSERT INTO paper_accounts (account_id, net_liquidation, buying_power, cash, maintenance_margin)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (account_id) DO NOTHING
            """,
            ("PAPER", initial, initial, initial, 0.0),
        )
        if not any(row["account_id"] == "PAPER" for row in existing_accounts):
            await self.initialize_risk_coverage("PAPER", fresh=True)
        await db.commit()

    async def initialize_risk_coverage(
        self, account_id: str, *, fresh: bool = False
    ) -> None:
        """Record when complete daily accounting begins, without backfilling guesses.

        fresh=True is only valid for a newly created or explicitly reset account.
        Existing accounts are blocked until the next UTC day on first migration.
        Repeated initialization does not move the coverage date.
        """
        db = await self._get_db()
        day = datetime.now(timezone.utc).date() + timedelta(days=0 if fresh else 1)
        await db.execute(
            "INSERT INTO paper_risk_coverage (account_id, complete_from, generation) VALUES (?, ?, ?) ON CONFLICT(account_id) DO NOTHING",
            (account_id, day.isoformat(), str(uuid.uuid4())),
        )

    async def get_balance(self, account_id: str) -> AccountBalance:
        db = await self._get_db()
        async with db.execute(
            "SELECT * FROM paper_accounts WHERE account_id = ?", (account_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return AccountBalance(
                    account_id=account_id,
                    net_liquidation=Decimal(0),
                    buying_power=Decimal(0),
                    cash=Decimal(0),
                    maintenance_margin=Decimal(0),
                )
            return AccountBalance(
                account_id=account_id,
                net_liquidation=Decimal(str(row["net_liquidation"])),
                buying_power=Decimal(str(row["buying_power"])),
                cash=Decimal(str(row["cash"])),
                maintenance_margin=Decimal(str(row["maintenance_margin"])),
            )

    async def get_positions(self, account_id: str) -> list[Position]:
        db = await self._get_db()
        positions = []
        async with db.execute(
            "SELECT * FROM paper_positions WHERE account_id = ? AND quantity != 0",
            (account_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                sym = Symbol(
                    ticker=row["symbol"], asset_type=AssetType(row["asset_type"])
                )
                positions.append(
                    Position(
                        symbol=sym,
                        quantity=Decimal(str(row["quantity"])),
                        avg_cost=Decimal(str(row["avg_cost"])),
                        market_value=Decimal(0),  # Needs real-time quote to update
                        unrealized_pnl=Decimal(0),
                        realized_pnl=Decimal(str(row["realized_pnl"])),
                    )
                )
        return positions

    async def record_fill(
        self,
        account_id: str,
        symbol: Symbol,
        side: OrderSide,
        quantity: Decimal,
        fill_price: Decimal,
        commission: Decimal = Decimal("0"),
        *,
        order_id: str | None = None,
        event_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        async with self.transaction():
            return await self._record_fill(
                account_id,
                symbol,
                side,
                quantity,
                fill_price,
                commission,
                order_id=order_id,
                event_id=event_id,
                occurred_at=occurred_at,
            )

    async def _record_fill(
        self,
        account_id: str,
        symbol: Symbol,
        side: OrderSide,
        quantity: Decimal,
        fill_price: Decimal,
        commission: Decimal = Decimal("0"),
        *,
        order_id: str | None = None,
        event_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        """Record a fill and its risk event in the caller's transaction."""
        db = await self._get_db()

        # Determine direction
        dir_mult = Decimal("1") if side == OrderSide.BUY else Decimal("-1")
        fill_qty = quantity * dir_mult

        cost = quantity * fill_price
        trade_pnl = Decimal("0")

        # 1. Update position
        async with db.execute(
            "SELECT quantity, avg_cost, realized_pnl FROM paper_positions WHERE account_id = ? AND symbol = ? AND asset_type = ?",
            (account_id, symbol.ticker, symbol.asset_type.value),
        ) as cursor:
            pos_row = await cursor.fetchone()

        if pos_row:
            cur_qty = Decimal(str(pos_row["quantity"]))
            cur_avg = Decimal(str(pos_row["avg_cost"]))
            cur_realized = Decimal(str(pos_row["realized_pnl"]))

            new_qty = cur_qty + fill_qty
            new_realized = cur_realized
            new_avg = cur_avg

            # Simple average cost logic
            if cur_qty == 0:
                new_avg = fill_price
            elif (cur_qty > 0 and fill_qty > 0) or (cur_qty < 0 and fill_qty < 0):
                # Increasing position
                total_val = (abs(cur_qty) * cur_avg) + (abs(fill_qty) * fill_price)
                new_avg = total_val / abs(new_qty)
            else:
                # Decreasing position -> realized PnL
                closed_qty = min(abs(cur_qty), abs(fill_qty))
                if cur_qty > 0:
                    trade_pnl = (fill_price - cur_avg) * closed_qty
                else:
                    trade_pnl = (cur_avg - fill_price) * closed_qty

                new_realized += trade_pnl
                if new_qty == 0:
                    new_avg = Decimal("0")
                elif (cur_qty > 0 and new_qty < 0) or (cur_qty < 0 and new_qty > 0):
                    # Flipped position
                    new_avg = fill_price

            await db.execute(
                """
                UPDATE paper_positions
                SET quantity = ?, avg_cost = ?, realized_pnl = ?
                WHERE account_id = ? AND symbol = ? AND asset_type = ?
                """,
                (
                    float(new_qty),
                    float(new_avg),
                    float(new_realized),
                    account_id,
                    symbol.ticker,
                    symbol.asset_type.value,
                ),
            )
        else:
            await db.execute(
                """
                INSERT INTO paper_positions (account_id, symbol, asset_type, quantity, avg_cost, realized_pnl)
                VALUES (?, ?, ?, ?, ?, 0.0)
                """,
                (
                    account_id,
                    symbol.ticker,
                    symbol.asset_type.value,
                    float(fill_qty),
                    float(fill_price),
                ),
            )

        # 2. Update cash
        async with db.execute(
            "SELECT cash, net_liquidation FROM paper_accounts WHERE account_id = ?",
            (account_id,),
        ) as cursor:
            acc_row = await cursor.fetchone()

        if acc_row:
            cur_cash = Decimal(str(acc_row["cash"]))
            # Decrease cash for buy, increase for sell; always deduct commission
            new_cash = cur_cash - (cost * dir_mult) - commission
            # Buying power is simplified here to be equal to cash
            # Recompute net_liquidation = cash + sum of position market values
            # For simplicity, adjust net_liq by the same delta as cash
            cur_net_liq = Decimal(str(acc_row["net_liquidation"]))
            cash_delta = new_cash - cur_cash
            new_net_liq = cur_net_liq + cash_delta
            await db.execute(
                "UPDATE paper_accounts SET cash = ?, buying_power = ?, net_liquidation = ? WHERE account_id = ?",
                (float(new_cash), float(new_cash), float(new_net_liq), account_id),
            )

        await self.record_risk_event(
            account_id,
            "fill",
            trade_pnl - commission,
            order_id=order_id,
            event_id=event_id,
            occurred_at=occurred_at,
        )

    async def record_risk_event(
        self,
        account_id: str,
        kind: str,
        net_pnl: Decimal,
        *,
        order_id: str | None = None,
        event_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        """Append evidence without committing independently of the cash/position write."""
        db = await self._get_db()
        await db.execute(
            "INSERT INTO paper_risk_events (event_id, account_id, order_id, kind, net_pnl, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                event_id or str(uuid.uuid4()),
                account_id,
                order_id,
                kind,
                str(net_pnl),
                (occurred_at or datetime.now(timezone.utc))
                .astimezone(timezone.utc)
                .isoformat(),
            ),
        )

    async def save_order_terms(
        self,
        order_id: str,
        order,
        *,
        submitted_at: datetime | None = None,
        epoch: str | None = None,
    ) -> None:
        async with self.transaction() as db:
            coverage = await (
                await db.execute(
                    "SELECT generation FROM paper_risk_coverage WHERE account_id=?",
                    (order.account_id,),
                )
            ).fetchone()
            if not coverage:
                raise ValueError("Paper order account has no risk coverage")
            actual_epoch = coverage["generation"]
            if epoch is not None and epoch != actual_epoch:
                raise ValueError("Paper order epoch does not match account")
            existing = await (
                await db.execute(
                    "SELECT account_id, epoch FROM paper_order_terms WHERE order_id=?",
                    (order_id,),
                )
            ).fetchone()
            if existing and (
                existing["account_id"] != order.account_id
                or existing["epoch"] != actual_epoch
            ):
                raise ValueError("Paper order identity cannot change")
            row = await (
                await db.execute(
                    "SELECT created_at FROM paper_orders WHERE order_id=?", (order_id,)
                )
            ).fetchone()
            stamp = (
                submitted_at.astimezone(timezone.utc).isoformat()
                if submitted_at is not None
                else row["created_at"]
                if row
                else datetime.now(timezone.utc).isoformat()
            )
            await db.execute(
                "INSERT INTO paper_order_terms (order_id, account_id, order_payload, submitted_at, epoch) VALUES (?, ?, ?, ?, ?) ON CONFLICT(order_id) DO UPDATE SET order_payload=EXCLUDED.order_payload",
                (
                    order_id,
                    order.account_id,
                    order_payload(order),
                    stamp,
                    actual_epoch,
                ),
            )

    async def get_order_snapshot(self, order_id: str):
        from execution.context import OrderSnapshot

        db = await self._get_db()
        row = await (
            await db.execute(
                "SELECT p.*, t.order_payload, t.submitted_at, t.epoch FROM paper_orders p JOIN paper_order_terms t ON p.order_id=t.order_id AND p.account_id=t.account_id WHERE p.order_id=?",
                (order_id,),
            )
        ).fetchone()
        if not row:
            return None
        order = decode_order(json.loads(row["order_payload"]))
        if (
            order.account_id != row["account_id"]
            or order.quantity != Decimal(str(row["quantity"]))
            or order.symbol.ticker != row["symbol"]
            or order.side.value != row["side"]
        ):
            raise ValueError("Paper order terms disagree with ledger")
        stamp = datetime.fromisoformat(str(row["submitted_at"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return OrderSnapshot(
            order_id,
            order,
            OrderStatus(row["status"]),
            Decimal(str(row["filled_quantity"])),
            submitted_at=stamp,
        )

    async def get_order_result(self, order_id: str) -> OrderResult | None:
        db = await self._get_db()
        row = await (
            await db.execute("SELECT * FROM paper_orders WHERE order_id=?", (order_id,))
        ).fetchone()
        if not row:
            return None
        fills = await (
            await db.execute(
                "SELECT commission, occurred_at FROM paper_fill_events WHERE order_id=? ORDER BY occurred_at, fill_id",
                (order_id,),
            )
        ).fetchall()
        return OrderResult(
            order_id=order_id,
            status=OrderStatus(row["status"]),
            filled_quantity=Decimal(str(row["filled_quantity"])),
            avg_fill_price=Decimal(str(row["avg_fill_price"]))
            if row["avg_fill_price"] is not None
            else None,
            commission=sum(
                (Decimal(str(fill["commission"])) for fill in fills), Decimal("0")
            ),
            filled_at=datetime.fromisoformat(fills[-1]["occurred_at"])
            if fills
            else None,
        )

    async def record_simulated_fill(
        self,
        fill_id: str,
        order_id: str,
        order,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal = Decimal("0"),
    ) -> OrderResult:
        async with self.transaction() as db:
            snapshot = await self.get_order_snapshot(order_id)
            if snapshot is None or encode_order(snapshot.order) != encode_order(order):
                raise ValueError("Paper fill terms do not match accepted order")
            if snapshot.status not in {OrderStatus.SUBMITTED, OrderStatus.PARTIAL}:
                raise ValueError("Paper order is no longer open")
            if (
                not all(
                    isinstance(value, Decimal) and value.is_finite()
                    for value in (quantity, price, commission)
                )
                or quantity <= 0
                or price <= 0
                or commission < 0
                or quantity > order.quantity - snapshot.filled_quantity
            ):
                raise ValueError("Invalid paper fill quantity, price, or commission")
            previous = await self.get_order_result(order_id)
            stamp = datetime.now(timezone.utc)
            await db.execute(
                "INSERT INTO paper_fill_events (fill_id, order_id, account_id, quantity, price, commission, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    fill_id,
                    order_id,
                    order.account_id,
                    str(quantity),
                    str(price),
                    str(commission),
                    stamp.isoformat(),
                ),
            )
            await self.record_fill(
                order.account_id,
                order.symbol,
                order.side,
                quantity,
                price,
                commission,
                order_id=order_id,
                event_id=fill_id,
                occurred_at=stamp,
            )
            total = previous.filled_quantity + quantity
            average = (
                (previous.avg_fill_price or Decimal("0")) * previous.filled_quantity
                + price * quantity
            ) / total
            status = (
                OrderStatus.FILLED if total == order.quantity else OrderStatus.PARTIAL
            )
            await self.save_order(
                order_id,
                order.account_id,
                order.symbol,
                order.side,
                order.quantity,
                status.value,
                total,
                average,
            )
            return await self.get_order_result(order_id)

    async def get_match_tick(self, tick_id: str):
        db = await self._get_db()
        row = await (
            await db.execute(
                "SELECT payload FROM paper_match_ticks WHERE tick_id=?", (tick_id,)
            )
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    async def save_match_tick(self, tick_id: str, payload) -> None:
        db = await self._get_db()
        await db.execute(
            "INSERT INTO paper_match_ticks (tick_id, payload) VALUES (?, ?)",
            (tick_id, json.dumps(payload, default=str, sort_keys=True)),
        )

    async def get_risk_state(self, account_id: str, market_data):
        db = await self._get_db()
        if isinstance(db, PostgresDB):
            async with self.transaction():
                return await self._get_risk_state(account_id, market_data)
        async with self._uow.exclusive():
            db = await self._get_db()
            if isinstance(db, aiosqlite.Connection) and db.in_transaction:
                raise RuntimeError(
                    "Paper connection already has an unrelated transaction"
                )
            return await self._get_risk_state(account_id, market_data)

    async def _get_risk_state(self, account_id: str, market_data):
        """Build a fresh, reconciled paper snapshot; missing evidence is an error.

        Daily loss is realized net PnL today plus outstanding unrealized losses.
        Unrealized gains cannot offset realized daily losses. This deliberately
        conservative policy does not pretend that entry cost is a midnight mark.
        """
        from execution.context import AccountRiskState
        from risk.rules import PortfolioContext

        db = await self._get_db()
        if not isinstance(db, (aiosqlite.Connection, PostgresDB)):
            raise ValueError(
                "Paper risk context requires supported transactional storage"
            )
        started = datetime.now(timezone.utc)
        day = started.date().isoformat()
        account = await (
            await db.execute(
                "SELECT account_id FROM paper_accounts WHERE account_id = ?",
                (account_id,),
            )
        ).fetchone()
        if not account:
            raise ValueError("Paper risk account is not initialized")
        coverage = await (
            await db.execute(
                "SELECT complete_from, generation FROM paper_risk_coverage WHERE account_id = ?",
                (account_id,),
            )
        ).fetchone()
        if not coverage or str(coverage["complete_from"]) > day:
            raise ValueError(
                "Paper daily risk coverage is incomplete; reconciliation required"
            )
        events = await (
            await db.execute(
                "SELECT * FROM paper_risk_events WHERE account_id = ? ORDER BY occurred_at, event_id",
                (account_id,),
            )
        ).fetchall()
        history = await (
            await db.execute(
                "SELECT * FROM paper_orders WHERE account_id = ?", (account_id,)
            )
        ).fetchall()
        terms_rows = await (
            await db.execute(
                "SELECT * FROM paper_order_terms WHERE account_id=? ORDER BY order_id",
                (account_id,),
            )
        ).fetchall()
        fills = await (
            await db.execute(
                "SELECT * FROM paper_fill_events WHERE account_id=? ORDER BY fill_id",
                (account_id,),
            )
        ).fetchall()
        terms = {row["order_id"]: row for row in terms_rows}
        rows_by_id = {row["order_id"]: row for row in history}
        if set(terms) - set(rows_by_id):
            raise ValueError("Paper accepted terms have no order ledger row")
        all_risk_fills = {
            event["event_id"]: event for event in events if event["kind"] == "fill"
        }
        fills_by_order = {}
        for fill in fills:
            linked = all_risk_fills.get(fill["fill_id"])
            if (
                not linked
                or linked["order_id"] != fill["order_id"]
                or linked["occurred_at"] != fill["occurred_at"]
                or fill["order_id"] not in terms
            ):
                raise ValueError("Paper simulated fill evidence is incomplete")
            quantity = Decimal(str(fill["quantity"]))
            price = Decimal(str(fill["price"]))
            commission = Decimal(str(fill["commission"]))
            if (
                not all(value.is_finite() for value in (quantity, price, commission))
                or quantity <= 0
                or price <= 0
                or commission < 0
            ):
                raise ValueError("Paper simulated fill amounts are invalid")
            fills_by_order.setdefault(fill["order_id"], []).append(fill)
        terminal_ids = set()
        open_orders = []
        counted_orders = set()
        today_events = [e for e in events if str(e["occurred_at"])[:10] == day]
        todays_risk_fills = [e for e in today_events if e["kind"] == "fill"]
        for row in history:
            order_id = row["order_id"]
            status = OrderStatus(row["status"])
            term = terms.get(order_id)
            filled = Decimal(str(row["filled_quantity"]))
            if term:
                if term["epoch"] != coverage["generation"]:
                    raise ValueError("Paper order belongs to a different account epoch")
                snapshot = await self.get_order_snapshot(order_id)
                if (
                    snapshot is None
                    or not filled.is_finite()
                    or filled < 0
                    or filled > snapshot.order.quantity
                ):
                    raise ValueError("Paper order filled quantity disagrees with terms")
                if (
                    (status == OrderStatus.SUBMITTED and filled != 0)
                    or (status == OrderStatus.PARTIAL and filled <= 0)
                    or (
                        status == OrderStatus.FILLED
                        and filled != snapshot.order.quantity
                    )
                ):
                    raise ValueError(
                        "Paper order status disagrees with filled quantity"
                    )
                created = snapshot.submitted_at
                if status in {OrderStatus.SUBMITTED, OrderStatus.PARTIAL}:
                    if filled >= snapshot.order.quantity:
                        raise ValueError("Paper open order has no remaining quantity")
                    open_orders.append(snapshot)
            else:
                if status in {OrderStatus.SUBMITTED, OrderStatus.PARTIAL}:
                    raise ValueError(
                        "Paper account has unresolved orders without terms; reconciliation required"
                    )
                created = datetime.fromisoformat(
                    str(row["created_at"]).replace("Z", "+00:00")
                )
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            if status in {
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
            }:
                terminal_ids.add(order_id)
            if (term is not None or filled > 0) and created.astimezone(
                timezone.utc
            ).date().isoformat() == day:
                counted_orders.add(order_id)
            linked_events = [
                event
                for event in events
                if event["kind"] == "fill" and event["order_id"] == order_id
            ]
            simulated = fills_by_order.get(order_id, [])
            if simulated:
                if {event["event_id"] for event in linked_events} != {
                    fill["fill_id"] for fill in simulated
                } or sum(
                    (Decimal(str(fill["quantity"])) for fill in simulated), Decimal("0")
                ) != filled:
                    raise ValueError(
                        "Paper cumulative fill evidence disagrees with ledger"
                    )
            else:
                # Historical immediate fills use a single risk event and no fill table.
                todays = [
                    event
                    for event in todays_risk_fills
                    if event["order_id"] == order_id
                ]
                expected = (
                    1
                    if filled > 0
                    and created.astimezone(timezone.utc).date().isoformat() == day
                    else 0
                )
                if len(todays) != expected:
                    raise ValueError(
                        "Paper daily fill evidence is incomplete; reconciliation required"
                    )
        if any(event["order_id"] not in rows_by_id for event in todays_risk_fills):
            raise ValueError(
                "Paper daily fill evidence is incomplete; reconciliation required"
            )
        counted_orders.update(event["order_id"] for event in todays_risk_fills)
        daily_pnl = sum(
            (Decimal(str(e["net_pnl"])) for e in today_events), Decimal("0")
        )
        if not daily_pnl.is_finite():
            raise ValueError("Invalid paper daily risk evidence")
        balance = await self.get_balance(account_id)
        positions = await self.get_positions(account_id)
        marked = []
        for position in positions:
            if market_data is None:
                raise ValueError("Paper position market data unavailable")
            quote = await market_data.get_quote(position.symbol)
            if quote is None or quote.symbol != position.symbol:
                raise ValueError("Paper position quote unavailable")
            if is_stale(timestamp_age_seconds(quote.timestamp)):
                raise ValueError("Paper position quote is stale")
            price = quote.bid if position.quantity > 0 else quote.ask
            price = price if price is not None else quote.last
            if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
                raise ValueError("Paper position quote is invalid")
            value = position.quantity * price
            marked.append(
                replace(
                    position,
                    market_value=value,
                    unrealized_pnl=(price - position.avg_cost) * position.quantity,
                )
            )
        # Do not accept a mixture of ledger revisions while awaiting quotes.
        after_events = await (
            await db.execute(
                "SELECT event_id FROM paper_risk_events WHERE account_id = ? ORDER BY occurred_at, event_id",
                (account_id,),
            )
        ).fetchall()
        after_history = await (
            await db.execute(
                "SELECT * FROM paper_orders WHERE account_id = ?", (account_id,)
            )
        ).fetchall()
        after_terms = await (
            await db.execute(
                "SELECT * FROM paper_order_terms WHERE account_id=? ORDER BY order_id",
                (account_id,),
            )
        ).fetchall()
        after_fills = await (
            await db.execute(
                "SELECT * FROM paper_fill_events WHERE account_id=? ORDER BY fill_id",
                (account_id,),
            )
        ).fetchall()
        if (
            [e["event_id"] for e in events] != [e["event_id"] for e in after_events]
            or [dict(row) for row in history] != [dict(row) for row in after_history]
            or [dict(row) for row in terms_rows] != [dict(row) for row in after_terms]
            or [dict(row) for row in fills] != [dict(row) for row in after_fills]
            or balance != await self.get_balance(account_id)
            or positions != await self.get_positions(account_id)
            or datetime.now(timezone.utc).date() != started.date()
        ):
            raise ValueError(
                "Paper account changed during risk snapshot; retry required"
            )
        unrealized_losses = sum(
            (min(Decimal("0"), p.unrealized_pnl) for p in marked), Decimal("0")
        )
        equity = balance.cash + sum((p.market_value for p in marked), Decimal("0"))
        return AccountRiskState(
            context=PortfolioContext(
                positions=marked,
                balance=replace(balance, net_liquidation=equity),
                daily_pnl=daily_pnl + unrealized_losses,
                daily_trade_count=len(counted_orders),
            ),
            observed_at=started,
            orders=open_orders,
            source="paper_risk_events",
            terminal_order_ids=terminal_ids,
            symbol_identity="ticker_asset",
            epoch=coverage["generation"],
        )

    async def save_order(
        self,
        order_id: str,
        account_id: str,
        symbol: Symbol,
        side: OrderSide,
        quantity: Decimal,
        status: str,
        filled: Decimal,
        avg_price: Decimal | None,
    ) -> None:
        db = await self._get_db()
        event = await (
            await db.execute(
                "SELECT occurred_at FROM paper_risk_events WHERE account_id=? AND order_id=? AND kind='fill' ORDER BY occurred_at LIMIT 1",
                (account_id, order_id),
            )
        ).fetchone()
        terms = await (
            await db.execute(
                "SELECT submitted_at FROM paper_order_terms WHERE order_id=? AND account_id=?",
                (order_id, account_id),
            )
        ).fetchone()
        occurred_at = (
            terms["submitted_at"]
            if terms
            else event["occurred_at"]
            if event
            else datetime.now(timezone.utc).isoformat()
        )
        await db.execute(
            """
            INSERT INTO paper_orders (order_id, account_id, symbol, side, quantity, status, filled_quantity, avg_fill_price, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (order_id) DO UPDATE SET quantity=EXCLUDED.quantity, status=EXCLUDED.status, filled_quantity=EXCLUDED.filled_quantity, avg_fill_price=EXCLUDED.avg_fill_price
            """,
            (
                order_id,
                account_id,
                symbol.ticker,
                side.value,
                float(quantity),
                status,
                float(filled),
                float(avg_price) if avg_price is not None else None,
                occurred_at,
            ),
        )

    async def get_order_history(self, account_id: str) -> list[OrderResult]:
        db = await self._get_db()
        async with db.execute(
            "SELECT * FROM paper_orders WHERE account_id = ?", (account_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                OrderResult(
                    order_id=r["order_id"],
                    status=OrderStatus(r["status"]),
                    filled_quantity=Decimal(str(r["filled_quantity"])),
                    avg_fill_price=Decimal(str(r["avg_fill_price"]))
                    if r["avg_fill_price"] is not None
                    else None,
                )
                for r in rows
            ]

    async def record_binary_resolution(
        self,
        account_id: str,
        symbol: Symbol,
        quantity: Decimal,
        entry_price: Decimal,
        resolution: str,  # "YES" | "NO" | "CANCELLED"
        commission: Decimal = Decimal("0"),
    ) -> None:
        async with self.transaction():
            return await self._record_binary_resolution(
                account_id, symbol, quantity, entry_price, resolution, commission
            )

    async def _record_binary_resolution(
        self,
        account_id: str,
        symbol: Symbol,
        quantity: Decimal,
        entry_price: Decimal,
        resolution: str,  # "YES" | "NO" | "CANCELLED"
        commission: Decimal = Decimal("0"),
    ) -> None:
        """Resolve a binary prediction contract position.

        YES resolves → each contract pays $1.00 (100¢).
        NO resolves  → contracts held YES pay $0.00; contracts held NO pay $1.00.
        CANCELLED    → full refund at entry_price per contract.

        Closes the position and credits/debits cash.
        """
        db = await self._get_db()

        # Idempotency: skip if already resolved for this (account_id, symbol)
        async with db.execute(
            "SELECT resolved_at FROM paper_positions WHERE account_id = ? AND symbol = ? AND asset_type = ?",
            (account_id, symbol.ticker, symbol.asset_type.value),
        ) as cursor:
            existing = await cursor.fetchone()
        if existing and existing["resolved_at"]:
            return

        if resolution == "YES":
            payout_per_contract = Decimal("1.00")
        elif resolution == "NO":
            payout_per_contract = Decimal("0.00")
        else:  # CANCELLED
            payout_per_contract = entry_price

        total_payout = payout_per_contract * quantity
        cost_basis = entry_price * quantity
        realized = total_payout - cost_basis - commission

        # Zero out position
        await db.execute(
            """
            UPDATE paper_positions
            SET quantity = 0,
                avg_cost = 0,
                realized_pnl = realized_pnl + ?
            WHERE account_id = ? AND symbol = ? AND asset_type = ?
            """,
            (float(realized), account_id, symbol.ticker, symbol.asset_type.value),
        )

        # Credit cash, buying_power, and net_liquidation with payout
        payout_net = float(total_payout - commission)
        await db.execute(
            """
            UPDATE paper_accounts
            SET cash = cash + ?,
                buying_power = buying_power + ?,
                net_liquidation = net_liquidation + ?
            WHERE account_id = ?
            """,
            (payout_net, payout_net, payout_net, account_id),
        )
        # Mark position as resolved to prevent duplicate settlements
        await db.execute(
            """
            UPDATE paper_positions
            SET resolved_at = datetime('now')
            WHERE account_id = ? AND symbol = ? AND asset_type = ?
            """,
            (account_id, symbol.ticker, symbol.asset_type.value),
        )
        await self.record_risk_event(account_id, "resolution", realized)

    # Backward compatibility alias
    record_kalshi_resolution = record_binary_resolution
