"""
JournalService — trade listing and detail with autopsy integration.

Consumed by WhatsApp /journal and GET /journal API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from journal.autopsy import _compute_pnl

if TYPE_CHECKING:
    from journal.autopsy import AutopsyGenerator
    from storage.opportunities import OpportunityStore
    from storage.pnl import TrackedPositionStore


@dataclass
class JournalEntry:
    position_id: int
    agent_name: str
    symbol: str
    side: str
    pnl: Decimal
    pnl_pct: float
    entry_time: str
    exit_time: str
    has_autopsy: bool


@dataclass
class JournalDetail:
    entry: JournalEntry
    entry_price: Decimal
    exit_price: Decimal
    quantity: int
    duration_hours: float
    max_adverse_excursion: Decimal
    exit_reason: str
    autopsy: str
    opportunity_reasoning: str | None


def _to_entry(position: dict, has_autopsy: bool = False) -> JournalEntry:
    pnl, pnl_pct = _compute_pnl(position)
    return JournalEntry(
        position_id=position["id"],
        agent_name=position["agent_name"],
        symbol=position["symbol"],
        side=position["side"],
        pnl=pnl,
        pnl_pct=pnl_pct,
        entry_time=position.get("entry_time", ""),
        exit_time=position.get("exit_time", ""),
        has_autopsy=has_autopsy,
    )


class JournalService:
    def __init__(
        self,
        pnl_store: TrackedPositionStore,
        opp_store: OpportunityStore,
        autopsy: AutopsyGenerator,
    ) -> None:
        self._pnl_store = pnl_store
        self._opp_store = opp_store
        self._autopsy = autopsy

    async def list_trades(
        self, agent_name: str | None = None, limit: int = 5,
    ) -> list[JournalEntry]:
        positions = await self._pnl_store.list_closed(agent_name=agent_name, limit=limit)
        entries: list[JournalEntry] = []
        for p in positions:
            cached = await self._autopsy.get_cached(p["id"])
            entries.append(_to_entry(p, has_autopsy=cached is not None))
        return entries

    async def get_trade_detail(self, position_id: int) -> JournalDetail | None:
        position = await self._pnl_store.get(position_id)
        if not position or position.get("status") != "closed":
            return None

        autopsy_text = await self._autopsy.get_or_generate(position)
        entry = _to_entry(position, has_autopsy=True)

        # Get opportunity reasoning
        opp_reasoning = None
        opp_id = position.get("opportunity_id")
        if opp_id:
            opp = await self._opp_store.get(opp_id)
            if opp:
                opp_reasoning = opp.get("reasoning")

        # Duration in hours
        try:
            entry_t = datetime.fromisoformat(position["entry_time"])
            exit_t = datetime.fromisoformat(position["exit_time"])
            duration_hours = (exit_t - entry_t).total_seconds() / 3600
        except Exception:
            duration_hours = 0.0

        return JournalDetail(
            entry=entry,
            entry_price=Decimal(position.get("entry_price", "0")),
            exit_price=Decimal(position.get("exit_price", "0")),
            quantity=int(position.get("entry_quantity", 0)),
            duration_hours=round(duration_hours, 2),
            max_adverse_excursion=Decimal(position.get("max_adverse_excursion", "0")),
            exit_reason=position.get("exit_reason", ""),
            autopsy=autopsy_text,
            opportunity_reasoning=opp_reasoning,
        )
