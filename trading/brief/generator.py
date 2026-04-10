"""
Morning Brief — daily LLM-generated trading intelligence digest.

Gathers context from: portfolio, journal, leaderboard, opportunities, markets.
Uses the unified LLMClient for resilient multi-provider LLM access.
Cached in daily_briefs SQLite table.
"""

from __future__ import annotations
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite
    from llm.client import LLMClient

logger = logging.getLogger(__name__)

BRIEF_PROMPT = """You are a trading co-pilot. Write a concise morning brief (3-5 sentences) for a trader. Cover:
1. Yesterday's portfolio performance (P&L, notable trades)
2. Agent activity (which agents performed well/poorly)
3. Active opportunities pending review
4. Prediction market highlights
5. Any risk flags

Tone: professional, concise, actionable. No markdown — plain text for WhatsApp/phone screens.

Context:
{context}

Write the brief now:"""


class BriefGenerator:
    def __init__(
        self,
        db: aiosqlite.Connection,
        llm: LLMClient | None = None,
    ) -> None:
        self._db = db
        if llm is not None:
            self._llm = llm
        else:
            from llm.client import LLMClient as _LLMClient

            self._llm = _LLMClient()

    async def get_or_generate(self) -> dict:
        """Return today's brief from cache, or generate fresh."""
        today = date.today().isoformat()
        cursor = await self._db.execute(
            "SELECT brief_text, created_at FROM daily_briefs WHERE date = ?", (today,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                "date": today,
                "brief": row[0],
                "created_at": row[1],
                "cached": True,
            }

        brief_text = await self.generate()
        now = datetime.utcnow().isoformat()
        await self._db.execute(
            "INSERT OR REPLACE INTO daily_briefs (date, brief_text, created_at) VALUES (?, ?, ?)",
            (today, brief_text, now),
        )
        await self._db.commit()
        return {"date": today, "brief": brief_text, "created_at": now, "cached": False}

    async def generate(self) -> str:
        """Gather context and call LLM."""
        context = await self._gather_context()
        prompt = BRIEF_PROMPT.format(context=context)

        try:
            result = await self._llm.complete(prompt, max_tokens=500)
            if result.text:
                return result.text
        except Exception as e:
            logger.warning("Brief LLM call failed: %s", e)

        return self._fallback_brief(context)

    async def _gather_context(self) -> str:
        """Read from SQLite tables to build context string."""
        sections = []

        # Recent closed trades (last 24h)
        cursor = await self._db.execute(
            "SELECT agent_name, symbol, side, entry_price, exit_price, entry_quantity "
            "FROM tracked_positions WHERE status = 'closed' "
            "ORDER BY exit_time DESC LIMIT 10"
        )
        trades = await cursor.fetchall()
        if trades:
            trade_lines = []
            for t in trades:
                entry = float(t[3]) if t[3] else 0
                exit_ = float(t[4]) if t[4] else 0
                qty = int(t[5]) if t[5] else 0
                direction = 1 if (t[2] or "").lower() == "buy" else -1
                pnl = (exit_ - entry) * qty * direction
                trade_lines.append(f"  {t[0]}: {t[2]} {t[1]} P&L=${pnl:+,.2f}")
            sections.append("Recent Closed Trades:\n" + "\n".join(trade_lines))

        # Performance snapshots (latest per agent)
        cursor = await self._db.execute(
            "SELECT agent_name, sharpe_ratio, total_pnl, win_rate "
            "FROM performance_snapshots WHERE id IN ("
            "  SELECT MAX(id) FROM performance_snapshots GROUP BY agent_name"
            ")"
        )
        perfs = await cursor.fetchall()
        if perfs:
            perf_lines = []
            for p in perfs:
                sharpe = float(p[1]) if p[1] else 0
                pnl = float(p[2]) if p[2] else 0
                wr = float(p[3]) if p[3] else 0
                perf_lines.append(
                    f"  {p[0]}: Sharpe={sharpe:.2f}, P&L=${pnl:+,.2f}, WR={wr:.0%}"
                )
            sections.append("Agent Performance:\n" + "\n".join(perf_lines))

        # Pending opportunities
        cursor = await self._db.execute(
            "SELECT agent_name, symbol, signal, confidence FROM opportunities "
            "WHERE status = 'pending' ORDER BY created_at DESC LIMIT 5"
        )
        opps = list(await cursor.fetchall())
        if opps:
            opp_lines = [f"  {o[0]}: {o[2]} {o[1]} (conf={o[3]:.0%})" for o in opps]
            sections.append(
                f"Pending Opportunities ({len(opps)}):\n" + "\n".join(opp_lines)
            )
        else:
            sections.append("Pending Opportunities: none")

        # Risk status
        cursor = await self._db.execute(
            "SELECT event_type, details FROM risk_events ORDER BY created_at DESC LIMIT 3"
        )
        risks = await cursor.fetchall()
        if risks:
            risk_lines = [f"  {r[0]}: {r[1]}" for r in risks]
            sections.append("Recent Risk Events:\n" + "\n".join(risk_lines))

        return "\n\n".join(sections) if sections else "No data available yet."

    def _fallback_brief(self, context: str) -> str:
        """Simple summary when no LLM is available."""
        lines = context.split("\n")
        summary_parts = [
            l.strip() for l in lines if l.strip() and not l.startswith(" ")
        ]
        return "Morning Brief: " + ". ".join(summary_parts[:4]) + "."

    async def get_history(self, days: int = 7) -> list[dict]:
        """Return last N briefs."""
        cursor = await self._db.execute(
            "SELECT date, brief_text, created_at FROM daily_briefs ORDER BY date DESC LIMIT ?",
            (days,),
        )
        rows = await cursor.fetchall()
        return [{"date": r[0], "brief": r[1], "created_at": r[2]} for r in rows]
