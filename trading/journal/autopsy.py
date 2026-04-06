"""
AutopsyGenerator — on-demand LLM-powered trade analysis.

Builds context from 4 sources:
  1. Trade outcome (TrackedPosition)
  2. Original opportunity (OpportunityStore)
  3. Market snapshot at entry (opportunity_snapshots)
  4. Agent's recent lessons (llm_lessons, read-only)

Uses unified LLMClient for completions.
Cached in trade_autopsies table after first generation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiosqlite
    from storage.opportunities import OpportunityStore

logger = logging.getLogger(__name__)


def _compute_pnl(position: dict) -> tuple[Decimal, float]:
    """Compute P&L and percentage from a closed position dict."""
    entry = Decimal(position.get("entry_price", "0"))
    exit_ = Decimal(position.get("exit_price", "0"))
    qty = int(position.get("entry_quantity", 0))
    entry_fees = Decimal(position.get("entry_fees", "0"))
    exit_fees = Decimal(position.get("exit_fees", "0"))
    direction = 1 if position.get("side", "").lower() == "buy" else -1

    gross = (exit_ - entry) * qty * direction
    pnl = gross - entry_fees - exit_fees
    cost = entry * qty
    pnl_pct = float(pnl / cost * 100) if cost else 0.0
    return pnl, pnl_pct


def _compute_duration(position: dict) -> str:
    """Human-readable duration string."""
    try:
        entry_t = datetime.fromisoformat(position["entry_time"])
        exit_t = datetime.fromisoformat(position["exit_time"])
        hours = (exit_t - entry_t).total_seconds() / 3600
        if hours < 24:
            return f"{hours:.1f} hours"
        return f"{hours / 24:.1f} days"
    except Exception:
        return "unknown"


class AutopsyGenerator:
    def __init__(
        self,
        db: "aiosqlite.Connection",
        opp_store: "OpportunityStore",
        *,
        llm: Any = None,  # LLMClient | None
        journal_manager=None,
    ) -> None:
        self._db = db
        self._opp_store = opp_store
        self._journal_manager = journal_manager

        if llm is not None:
            self._llm = llm
        else:
            from llm.client import LLMClient as _LLMClient

            self._llm = _LLMClient()

    async def get_or_generate(self, position: dict) -> str:
        """Cache-first: return cached autopsy or generate + cache."""
        cached = await self.get_cached(position["id"])
        if cached:
            return cached
        text = await self.generate(position)

        if self._journal_manager:
            try:
                from journal.models import TradeExecution

                pnl, pnl_pct = _compute_pnl(position)

                exec_log = TradeExecution(
                    agent_name=position["agent_name"],
                    symbol=position["symbol"],
                    position_id=str(position["id"]),
                    opportunity_id=str(position.get("opportunity_id", "")),
                    entry_time=datetime.fromisoformat(position["entry_time"]),
                    exit_time=datetime.fromisoformat(position["exit_time"]),
                    pnl_realized=float(pnl),
                    autopsy=text,
                )
                await self._journal_manager.log_trade_execution(exec_log)
            except Exception as e:
                logger.warning(
                    "Failed to store vector trade log for %s: %s", position["id"], e
                )

        return text

    async def get_cached(self, position_id: int) -> str | None:
        row = await self._db.execute(
            "SELECT autopsy_text FROM trade_autopsies WHERE position_id = ?",
            (position_id,),
        )
        data = await row.fetchone()
        return data[0] if data else None

    async def generate(self, position: dict) -> str:
        """Force generation (bypasses cache lookup, but caches result)."""
        if position.get("status") != "closed":
            return "Autopsy pending (position still open)."

        prompt = await self._build_prompt(position)

        try:
            result = await self._llm.complete(prompt, max_tokens=200)
            text = result.text or self._fallback_summary(position)
        except Exception as exc:
            logger.warning(
                "LLM autopsy failed for position %s: %s", position["id"], exc
            )
            return self._fallback_summary(position)

        await self._cache(position["id"], text)
        return text

    async def _build_prompt(self, position: dict) -> str:
        """Assemble context from 4 sources."""
        pnl, pnl_pct = _compute_pnl(position)
        duration = _compute_duration(position)

        # Source 1: Trade outcome
        trade_block = (
            f"Symbol: {position['symbol']} | Side: {position['side']} | "
            f"Entry: ${position['entry_price']} → Exit: ${position['exit_price']}\n"
            f"P&L: ${pnl:.2f} ({pnl_pct:+.1f}%) | Duration: {duration} | "
            f"Max Drawdown: {position.get('max_adverse_excursion', 'N/A')}"
        )

        # Source 2: Original opportunity
        opp_block = "Not available"
        opp_id = position.get("opportunity_id")
        if opp_id:
            opp = await self._opp_store.get(opp_id)
            if opp:
                opp_block = (
                    f"{opp.get('reasoning', 'N/A')}\n"
                    f"Signal: {opp.get('signal', 'N/A')} | "
                    f"Confidence: {opp.get('confidence', 'N/A')}"
                )

        # Source 3: Market snapshot at entry
        snapshot_block = "Not available"
        if opp_id:
            snapshot = await self._opp_store.get_snapshot(opp_id)
            if snapshot and snapshot.get("quote"):
                q = snapshot["quote"]

                def _fmt(v: object) -> str:
                    try:
                        return f"{float(v):.2f}"
                    except (TypeError, ValueError):
                        return str(v) if v is not None else "N/A"

                snapshot_block = (
                    f"Bid: {_fmt(q.get('bid'))} | Ask: {_fmt(q.get('ask'))} | "
                    f"Last: {_fmt(q.get('last'))} | Volume: {q.get('volume', 'N/A')}"
                )

        # Source 4: Agent's recent lessons (read-only, max 5)
        lessons_block = "None yet"
        try:
            cursor = await self._db.execute(
                "SELECT lesson, category FROM llm_lessons "
                "WHERE agent_name = ? ORDER BY created_at DESC LIMIT 5",
                (position["agent_name"],),
            )
            rows = await cursor.fetchall()
            if rows:
                lessons = []
                for r in rows:
                    lesson = r["lesson"] if isinstance(r, dict) else r[0]
                    cat = r["category"] if isinstance(r, dict) else r[1]
                    lessons.append(f"- [{cat}] {lesson}")
                lessons_block = "\n".join(lessons)
        except Exception as exc:
            logger.debug(
                "Failed to fetch agent lessons for %s: %s",
                position.get("agent_name"),
                exc,
            )

        return (
            "You are analyzing a completed trade for a trading journal.\n\n"
            f"TRADE:\n{trade_block}\n\n"
            f"AGENT REASONING (at entry):\n{opp_block}\n\n"
            f"MARKET AT ENTRY:\n{snapshot_block}\n\n"
            f"AGENT'S RECENT LESSONS:\n{lessons_block}\n\n"
            "Write a 2-3 sentence autopsy: what happened, why the trade worked or failed, "
            "and one actionable takeaway. Be specific about prices and timing, not generic."
        )

    async def _cache(self, position_id: int, text: str) -> None:
        try:
            await self._db.execute(
                "INSERT OR REPLACE INTO trade_autopsies (position_id, autopsy_text) VALUES (?, ?)",
                (position_id, text),
            )
            await self._db.commit()
        except Exception as exc:
            logger.warning("Failed to cache autopsy for %s: %s", position_id, exc)

    def _fallback_summary(self, position: dict) -> str:
        """Computed summary when no LLM is available."""
        pnl, pnl_pct = _compute_pnl(position)
        duration = _compute_duration(position)
        side = position.get("side", "").upper()
        return (
            f"{side} {position['symbol']} at ${position['entry_price']}, "
            f"closed at ${position['exit_price']}. "
            f"P&L: ${pnl:.2f} ({pnl_pct:+.1f}%). Duration: {duration}."
        )
