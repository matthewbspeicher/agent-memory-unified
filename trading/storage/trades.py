from __future__ import annotations
import json
from decimal import Decimal
from typing import Any

import aiosqlite

class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class TradeStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def save_trade(self, opportunity_id: str, order_result: dict, risk_evaluation: dict | None = None, agent_name: str | None = None) -> None:
        await self._db.execute(
            "INSERT INTO trades (opportunity_id, order_result, risk_evaluation, agent_name) VALUES (?, ?, ?, ?)",
            (opportunity_id, json.dumps(order_result, cls=_DecimalEncoder), json.dumps(risk_evaluation, cls=_DecimalEncoder), agent_name),
        )
        await self._db.commit()

    async def get_trades(self, opportunity_id: str | None = None, agent_name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if opportunity_id:
            cursor = await self._db.execute(
                "SELECT * FROM trades WHERE opportunity_id = ? ORDER BY created_at DESC LIMIT ?",
                (opportunity_id, limit),
            )
        elif agent_name:
            cursor = await self._db.execute(
                "SELECT * FROM trades WHERE agent_name = ? ORDER BY created_at DESC LIMIT ?",
                (agent_name, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,),
            )
        return [dict(row) for row in await cursor.fetchall()]

    async def save_risk_event(self, event_type: str, details: dict | None = None) -> None:
        await self._db.execute(
            "INSERT INTO risk_events (event_type, details) VALUES (?, ?)",
            (event_type, json.dumps(details)),
        )
        await self._db.commit()

    async def get_risk_events(self, limit: int = 50) -> list[dict[str, Any]]:
        cursor = await self._db.execute(
            "SELECT * FROM risk_events ORDER BY created_at DESC LIMIT ?", (limit,),
        )
        return [dict(row) for row in await cursor.fetchall()]
