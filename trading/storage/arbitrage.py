"""ArbStore — persists dual-leg arbitrage trades and their execution states."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

import aiosqlite
from execution.models import ArbTrade, ArbLeg, ArbState
from broker.models import OrderBase

logger = logging.getLogger(__name__)

class ArbStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def save_trade(self, trade: ArbTrade) -> None:
        """Persist a new arbitrage trade and its legs."""
        try:
            # 1. Save main trade record
            await self._db.execute(
                """INSERT INTO arb_trades
                   (id, symbol_a, symbol_b, expected_profit_bps, sequencing, state, error_message, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade.id, trade.symbol_a, trade.symbol_b, trade.expected_profit_bps,
                    trade.sequencing.value, trade.state.value, trade.error_message,
                    trade.created_at.isoformat(), trade.updated_at.isoformat()
                )
            )

            import dataclasses
            from enum import Enum
            def _encoder(obj):
                if isinstance(obj, Decimal): return str(obj)
                if isinstance(obj, Enum): return obj.value
                return str(obj)

            # 2. Save legs
            for leg_name, leg in [("leg_a", trade.leg_a), ("leg_b", trade.leg_b)]:
                order_dict = dataclasses.asdict(leg.order)
                order_json = json.dumps(order_dict, default=_encoder)
                await self._db.execute(
                    """INSERT INTO arb_legs
                       (trade_id, leg_name, broker_id, order_data, fill_price, fill_quantity, status, external_order_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        trade.id, leg_name, leg.broker_id, order_json,
                        str(leg.fill_price) if leg.fill_price else None,
                        str(leg.fill_quantity), leg.status, leg.external_order_id
                    )
                )
            
            await self._db.commit()
        except Exception as exc:
            logger.error("ArbStore.save_trade failed: %s", exc)
            raise

    async def update_trade_state(self, trade_id: str, state: ArbState, error_message: Optional[str] = None) -> None:
        """Update the state of an existing trade."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE arb_trades SET state = ?, error_message = ?, updated_at = ? WHERE id = ?",
            (state.value, error_message, now, trade_id)
        )
        await self._db.commit()

    async def update_leg(self, trade_id: str, leg_name: str, leg: ArbLeg) -> None:
        """Update fill data or status for a specific leg."""
        await self._db.execute(
            """UPDATE arb_legs SET 
               fill_price = ?, fill_quantity = ?, status = ?, external_order_id = ?
               WHERE trade_id = ? AND leg_name = ?""",
            (
                str(leg.fill_price) if leg.fill_price else None,
                str(leg.fill_quantity), leg.status, leg.external_order_id,
                trade_id, leg_name
            )
        )
        await self._db.commit()

    async def update_leg_atomic(self, trade_id: str, leg_name: str, leg: ArbLeg) -> None:
        """Atomic, column-level update for a specific leg and marks trade as updated."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            
            # 1. Update the leg columns
            await self._db.execute(
                """UPDATE arb_legs SET 
                   fill_price = ?, fill_quantity = ?, status = ?, external_order_id = ?
                   WHERE trade_id = ? AND leg_name = ?""",
                (
                    str(leg.fill_price) if leg.fill_price else None,
                    str(leg.fill_quantity), leg.status, leg.external_order_id,
                    trade_id, leg_name
                )
            )

            # 2. Update the trade updated_at field
            await self._db.execute(
                "UPDATE arb_trades SET updated_at = ? WHERE id = ?",
                (now, trade_id)
            )
            
            await self._db.commit()
        except Exception as exc:
            logger.error("ArbStore.update_leg_atomic failed for %s:%s: %s", trade_id, leg_name, exc)
            raise

    async def get_trade(self, trade_id: str) -> Optional[ArbTrade]:
        """Retrieve a full ArbTrade object with its legs."""
        cursor = await self._db.execute("SELECT * FROM arb_trades WHERE id = ?", (trade_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        # Fetch legs
        cursor = await self._db.execute("SELECT * FROM arb_legs WHERE trade_id = ?", (trade_id,))
        leg_rows = await cursor.fetchall()
        
        legs = {}
        for lr in leg_rows:
            order_dict = json.loads(lr["order_data"])
            # Reconstruct basic order (Note: specialized types might need more care)
            order = OrderBase(**order_dict)
            
            legs[lr["leg_name"]] = ArbLeg(
                broker_id=lr["broker_id"],
                order=order,
                fill_price=Decimal(lr["fill_price"]) if lr["fill_price"] else None,
                fill_quantity=Decimal(lr["fill_quantity"]),
                status=lr["status"],
                external_order_id=lr["external_order_id"]
            )

        from execution.models import SequencingStrategy
        return ArbTrade(
            id=row["id"],
            symbol_a=row["symbol_a"],
            symbol_b=row["symbol_b"],
            leg_a=legs["leg_a"],
            leg_b=legs["leg_b"],
            expected_profit_bps=row["expected_profit_bps"],
            sequencing=SequencingStrategy(row["sequencing"]),
            state=ArbState(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error_message=row["error_message"]
        )
