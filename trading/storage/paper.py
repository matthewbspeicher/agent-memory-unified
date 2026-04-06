from decimal import Decimal
from broker.models import (
    AccountBalance,
    Position,
    Symbol,
    AssetType,
    OrderResult,
    OrderStatus,
    OrderSide,
)

import aiosqlite


class PaperStore:
    def __init__(self, db=None):
        self._db = db
        self._is_postgres = not isinstance(db, aiosqlite.Connection) if db else False

    async def _get_db(self):
        if self._db:
            return self._db
        from storage.db import get_db

        return await get_db()

    async def init_tables(self) -> None:
        db = await self._get_db()
        ts_default = "NOW()" if self._is_postgres else "(datetime('now'))"
        for sql in [
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
            await db.execute(sql)

        # Migrate: add resolved_at column if not present (idempotent ALTER TABLE)
        try:
            await db.execute("ALTER TABLE paper_positions ADD COLUMN resolved_at TEXT")
            await db.commit()
        except Exception as exc:
            _msg = str(exc).lower()
            if "duplicate column name" not in _msg and "already exists" not in _msg:
                raise

        # Ensure default paper account exists
        await db.execute(
            """
            INSERT INTO paper_accounts (account_id, net_liquidation, buying_power, cash, maintenance_margin)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (account_id) DO NOTHING
            """,
            ("PAPER", 100000.0, 100000.0, 100000.0, 0.0),
        )
        await db.commit()

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
    ) -> None:
        """Record an order fill, updating positions and cash."""
        db = await self._get_db()

        # Determine direction
        dir_mult = Decimal("1") if side == OrderSide.BUY else Decimal("-1")
        fill_qty = quantity * dir_mult

        cost = quantity * fill_price

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

        await db.commit()

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
        await db.execute(
            """
            INSERT INTO paper_orders (order_id, account_id, symbol, side, quantity, status, filled_quantity, avg_fill_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (order_id) DO UPDATE SET status=EXCLUDED.status, filled_quantity=EXCLUDED.filled_quantity, avg_fill_price=EXCLUDED.avg_fill_price
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
            ),
        )
        await db.commit()

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
        await db.commit()

    # Backward compatibility alias
    record_kalshi_resolution = record_binary_resolution
