from __future__ import annotations
from typing import Any
from decimal import Decimal
from functools import wraps

from storage.paper import PaperStore
from storage.postgres import PostgresDB
from storage.unit_of_work import UnitOfWork


def atomic(method):
    @wraps(method)
    async def wrapped(self, *args, **kwargs):
        await self.init_tables()
        async with self.transaction():
            return await method(self, *args, **kwargs)

    return wrapped


import aiosqlite


class TrackedPositionStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._uow = UnitOfWork(db)
        # Reads the Paper ledger on this store's own transaction.
        self._ledger = PaperStore(unit_of_work=self._uow)
        self._initialized = False

    async def _get_db(self):
        return await self._uow.handle()

    async def close(self) -> None:
        await self._uow.close()

    def transaction(self):
        return self._uow.transaction()

    @atomic
    async def open_position(
        self,
        *,
        agent_name: str,
        opportunity_id: str,
        symbol: str,
        side: str,
        entry_price: str,
        entry_quantity: str | Decimal | int,
        entry_fees: str,
        entry_time: str,
        expires_at: str | None = None,
        broker_id: str | None = None,
        account_id: str | None = None,
    ) -> int:
        """INSERT a new position. Returns the lastrowid."""
        params = (
            agent_name,
            opportunity_id,
            symbol,
            side,
            entry_price,
            str(entry_quantity),
            entry_fees,
            entry_time,
            expires_at,
            broker_id,
            account_id,
            str(entry_quantity),
        )
        if hasattr((await self._get_db()), "fetchone"):
            row = await (await self._get_db()).fetchone(
                """INSERT INTO tracked_positions
                   (agent_name, opportunity_id, symbol, side, entry_price, entry_quantity, entry_fees, entry_time, expires_at, broker_id, account_id, remaining_quantity)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                params,
            )
            return int(row["id"]) if row else 0

        cursor = await (await self._get_db()).execute(
            """INSERT INTO tracked_positions
               (agent_name, opportunity_id, symbol, side, entry_price, entry_quantity, entry_fees, entry_time, expires_at, broker_id, account_id, remaining_quantity)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            params,
        )
        row_id = cursor.lastrowid
        if row_id is None:
            raise RuntimeError("Failed to insert position: no row ID returned")
        return row_id

    @atomic
    async def close_position(
        self,
        position_id: int,
        *,
        exit_price: str,
        exit_fees: str,
        exit_time: str,
        exit_reason: str,
    ) -> None:
        """UPDATE position status to 'closed' with exit details."""
        await (await self._get_db()).execute(
            """UPDATE tracked_positions
               SET exit_price = ?, exit_fees = ?, exit_time = ?, exit_reason = ?, status = 'closed', remaining_quantity = '0'
               WHERE id = ?""",
            (exit_price, exit_fees, exit_time, exit_reason, position_id),
        )

    @atomic
    async def get(self, position_id: int) -> dict[str, Any] | None:
        """SELECT position by id."""
        async with (await self._get_db()).execute(
            "SELECT * FROM tracked_positions WHERE id = ?", (position_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return (
                {**dict(row), "entry_quantity": Decimal(str(row["entry_quantity"]))}
                if row
                else None
            )

    @atomic
    async def list_open(
        self, agent_name: str | None = None, symbol: str | None = None
    ) -> list[dict[str, Any]]:
        """SELECT open positions with optional filters. ORDER BY entry_time ASC."""
        query = "SELECT * FROM tracked_positions WHERE status = 'open'"
        params: list[str | None] = []

        if agent_name is not None:
            query += " AND agent_name = ?"
            params.append(agent_name)

        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)

        query += " ORDER BY entry_time ASC"

        async with (await self._get_db()).execute(query, params) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    @atomic
    async def list_closed(
        self, agent_name: str | None = None, limit: int = 100, since: str | None = None
    ) -> list[dict[str, Any]]:
        """SELECT closed positions with optional agent filter. ORDER BY exit_time DESC."""
        query = "SELECT * FROM tracked_positions WHERE status = 'closed'"
        params: list = []
        if agent_name is not None:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if since is not None:
            query += " AND exit_time >= ?"
            params.append(since)
        query += " ORDER BY exit_time DESC LIMIT ?"
        params.append(limit)
        async with (await self._get_db()).execute(query, params) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    @atomic
    async def update_mae(self, position_id: int, mae: str) -> None:
        """UPDATE max_adverse_excursion."""
        await (await self._get_db()).execute(
            "UPDATE tracked_positions SET max_adverse_excursion = ? WHERE id = ?",
            (mae, position_id),
        )

    @atomic
    async def get_open_quantity_by_symbol(self) -> dict[str, Decimal]:
        result = {}
        for row in await self.list_open():
            result[row["symbol"]] = result.get(row["symbol"], Decimal(0)) + Decimal(
                row["remaining_quantity"]
            )
        return result

    async def init_tables(self):
        if self._initialized:
            return
        async with self._uow.exclusive():
            if self._initialized:
                return
            await self._uow.adopt_dedicated_connection(busy_timeout=False)
        async with self.transaction() as db:
            if isinstance(db, PostgresDB):
                await db.execute(
                    "ALTER TABLE tracked_positions ALTER COLUMN entry_quantity TYPE TEXT USING entry_quantity::text"
                )
                for name, definition in [
                    ("remaining_quantity", "TEXT"),
                    ("exited_quantity", "TEXT NOT NULL DEFAULT '0'"),
                    ("realized_pnl", "TEXT NOT NULL DEFAULT '0'"),
                ]:
                    await db.execute(
                        f"ALTER TABLE tracked_positions ADD COLUMN IF NOT EXISTS {name} {definition}"
                    )
            else:
                columns = {
                    row[1]: row[2]
                    for row in await (
                        await db.execute("PRAGMA table_info(tracked_positions)")
                    ).fetchall()
                }
                if columns.get("entry_quantity", "").upper() != "TEXT":
                    await db.execute(
                        "ALTER TABLE tracked_positions RENAME COLUMN entry_quantity TO legacy_entry_quantity"
                    )
                    await db.execute(
                        "ALTER TABLE tracked_positions ADD COLUMN entry_quantity TEXT NOT NULL DEFAULT '0'"
                    )
                    await db.execute(
                        "UPDATE tracked_positions SET entry_quantity = CAST(legacy_entry_quantity AS TEXT)"
                    )
                    await db.execute(
                        "ALTER TABLE tracked_positions DROP COLUMN legacy_entry_quantity"
                    )
                for name, definition in [
                    ("remaining_quantity", "TEXT"),
                    ("exited_quantity", "TEXT NOT NULL DEFAULT '0'"),
                    ("realized_pnl", "TEXT NOT NULL DEFAULT '0'"),
                ]:
                    if name not in columns:
                        await db.execute(
                            f"ALTER TABLE tracked_positions ADD COLUMN {name} {definition}"
                        )
            await db.execute(
                "UPDATE tracked_positions SET remaining_quantity = CASE WHEN status='closed' THEN '0' ELSE entry_quantity END WHERE remaining_quantity IS NULL"
            )
            await db.execute("""CREATE TABLE IF NOT EXISTS tracked_fill_receipts (
                broker_id TEXT NOT NULL, account_id TEXT NOT NULL, order_id TEXT NOT NULL,
                role TEXT NOT NULL, position_id INTEGER NOT NULL,
                quantity TEXT NOT NULL, notional TEXT NOT NULL, fees TEXT NOT NULL,
                PRIMARY KEY (broker_id, account_id, order_id))""")
        self._initialized = True

    @atomic
    async def apply_entry_fill(
        self,
        *,
        broker_id,
        account_id,
        order_id,
        cumulative_quantity,
        cumulative_avg_price,
        cumulative_fees,
        filled_at,
        agent_name,
        opportunity_id,
        symbol,
        side,
        expires_at=None,
        expected_epoch=None,
    ):
        metadata = dict(
            agent_name=agent_name,
            opportunity_id=opportunity_id,
            symbol=symbol,
            side=side,
            expires_at=expires_at,
        )
        return await self._apply_fill(
            "entry",
            None,
            broker_id,
            account_id,
            order_id,
            cumulative_quantity,
            cumulative_avg_price,
            cumulative_fees,
            filled_at,
            metadata,
            expected_epoch,
        )

    @atomic
    async def apply_exit_fill(
        self,
        position_id,
        *,
        broker_id,
        account_id,
        order_id,
        cumulative_quantity,
        cumulative_avg_price,
        cumulative_fees,
        filled_at,
        exit_reason,
        expected_epoch=None,
    ):
        return await self._apply_fill(
            "exit",
            position_id,
            broker_id,
            account_id,
            order_id,
            cumulative_quantity,
            cumulative_avg_price,
            cumulative_fees,
            filled_at,
            {"exit_reason": exit_reason},
            expected_epoch,
        )

    async def _apply_fill(
        self,
        role,
        position_id,
        broker,
        account,
        order,
        quantity,
        price,
        fees,
        stamp,
        metadata,
        expected_epoch=None,
    ):
        db = await self._get_db()
        if expected_epoch is not None:
            if await self._ledger.account_generation(account) != expected_epoch:
                raise ValueError(
                    "Paper account generation changed before fill projection"
                )
        stamp = stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp)
        if not all(
            isinstance(value, str) and value for value in (broker, account, order)
        ):
            raise ValueError("Fill requires broker, account and order identity")
        if role == "entry" and metadata["side"].upper() not in {
            "BUY",
            "SELL",
            "LONG",
            "SHORT",
        }:
            raise ValueError("Unknown position direction")
        quantity, price, fees = map(
            lambda value: Decimal(str(value)), (quantity, price, fees)
        )
        if (
            not all(v.is_finite() for v in (quantity, price, fees))
            or quantity < 0
            or price <= 0
            or fees < 0
        ):
            raise ValueError("Invalid cumulative fill amounts")
        receipt = await (
            await db.execute(
                "SELECT * FROM tracked_fill_receipts WHERE broker_id=? AND account_id=? AND order_id=?",
                (broker, account, order),
            )
        ).fetchone()
        notional = quantity * price
        if receipt:
            if receipt["role"] != role or (
                position_id is not None and receipt["position_id"] != position_id
            ):
                raise ValueError("Fill receipt identity mismatch")
            position_id = receipt["position_id"]
            old_q, old_n, old_f = (
                Decimal(receipt[key]) for key in ("quantity", "notional", "fees")
            )
        else:
            old_q = old_n = old_f = Decimal(0)
        delta, delta_n, delta_f = quantity - old_q, notional - old_n, fees - old_f
        if (
            delta < 0
            or delta_f < 0
            or (delta == 0 and (delta_n != 0 or delta_f != 0))
            or (delta > 0 and delta_n <= 0)
        ):
            raise ValueError("Out-of-order or conflicting cumulative fill")
        row = await self.get(position_id) if position_id is not None else None
        if receipt and row is None:
            raise ValueError("Fill receipt refers to missing position")
        if row and (row["broker_id"] != broker or row["account_id"] != account):
            raise ValueError("Fill account does not own position")
        if (
            role == "entry"
            and row
            and any(
                row[key] != metadata[key]
                for key in ("agent_name", "opportunity_id", "symbol", "side")
            )
        ):
            raise ValueError("Entry fill identity changed")
        if delta == 0:
            return row
        if role == "entry":
            if row is None:
                position_id = await self.open_position(
                    **metadata,
                    entry_price=str(price),
                    entry_quantity=quantity,
                    entry_fees=str(fees),
                    entry_time=stamp,
                    broker_id=broker,
                    account_id=account,
                )
            else:
                if row["status"] != "open" or Decimal(row["exited_quantity"]) != 0:
                    raise ValueError("Cannot extend entry after an exit")
                total = Decimal(row["entry_quantity"]) + delta
                average = (
                    Decimal(row["entry_price"]) * Decimal(row["entry_quantity"])
                    + delta_n
                ) / total
                await db.execute(
                    "UPDATE tracked_positions SET entry_quantity=?, remaining_quantity=?, entry_price=?, entry_fees=? WHERE id=?",
                    (
                        str(total),
                        str(Decimal(row["remaining_quantity"]) + delta),
                        str(average),
                        str(Decimal(row["entry_fees"]) + delta_f),
                        position_id,
                    ),
                )
        else:
            if (
                row is None
                or row["status"] != "open"
                or delta > Decimal(row["remaining_quantity"])
            ):
                raise ValueError("Exit fill exceeds open position")
            remaining = Decimal(row["remaining_quantity"]) - delta
            exited = Decimal(row["exited_quantity"]) + delta
            average = (
                (Decimal(row["exit_price"] or "0") * Decimal(row["exited_quantity"]))
                + delta_n
            ) / exited
            direction = (
                Decimal(1) if row["side"].upper() in {"BUY", "LONG"} else Decimal(-1)
            )
            realized = (
                Decimal(row["realized_pnl"])
                + direction * (delta_n - Decimal(row["entry_price"]) * delta)
                - delta_f
                - Decimal(row["entry_fees"]) * delta / Decimal(row["entry_quantity"])
            )
            await db.execute(
                "UPDATE tracked_positions SET remaining_quantity=?, exited_quantity=?, exit_price=?, exit_fees=?, exit_time=?, exit_reason=?, realized_pnl=?, status=? WHERE id=?",
                (
                    str(remaining),
                    str(exited),
                    str(average),
                    str(Decimal(row["exit_fees"] or "0") + delta_f),
                    stamp,
                    metadata["exit_reason"],
                    str(realized),
                    "closed" if remaining == 0 else "open",
                    position_id,
                ),
            )
        await db.execute(
            "INSERT INTO tracked_fill_receipts (broker_id,account_id,order_id,role,position_id,quantity,notional,fees) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (broker_id,account_id,order_id) DO UPDATE SET quantity=EXCLUDED.quantity,notional=EXCLUDED.notional,fees=EXCLUDED.fees",
            (
                broker,
                account,
                order,
                role,
                position_id,
                str(quantity),
                str(notional),
                str(fees),
            ),
        )
        return await self.get(position_id)

    @atomic
    async def has_pending_execution(self, position_id: int) -> bool:
        db = await self._get_db()
        if isinstance(db, PostgresDB):
            table = await db.fetchone("SELECT to_regclass('paper_fill_jobs') AS name")
            exists = table and table["name"] is not None
        else:
            exists = await (
                await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_fill_jobs'"
                )
            ).fetchone()
        if not exists:
            return False
        row = await (
            await db.execute(
                "SELECT job_id FROM paper_fill_jobs WHERE done=0 AND (position_id=? OR (role='entry' AND job_id=(SELECT opportunity_id FROM tracked_positions WHERE id=?))) LIMIT 1",
                (position_id, position_id),
            )
        ).fetchone()
        return row is not None

    @atomic
    async def has_only_pending_entry(self, position_id: int) -> bool:
        db = await self._get_db()
        rows = await (
            await db.execute(
                "SELECT role FROM paper_fill_jobs WHERE done=0 AND (position_id=? OR job_id=(SELECT opportunity_id FROM tracked_positions WHERE id=?))",
                (position_id, position_id),
            )
        ).fetchall()
        return len(rows) == 1 and rows[0]["role"] == "entry"
