"""
Agent War Room — convergence signal detection across agents.

Detects when 2+ agents flag the same symbol in the same direction within a time window.
On-demand LLM synthesis reads both agents' reasoning and produces combined analysis.
Uses unified LLMClient.
"""
from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite
    from llm.client import LLMClient

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are a trading analyst. Two or more agents have independently identified the same trading signal. Synthesize their reasoning into a combined analysis.

Symbol: {symbol}
Direction: {direction}
Agents and their reasoning:
{agent_reasoning}

Write a concise 2-3 sentence synthesis explaining why multiple agents converge on this signal and what it implies. No markdown — plain text."""


@dataclass
class ConvergenceSignal:
    id: str
    symbol: str
    direction: str  # "BUY" or "SELL"
    agents: list[str]
    opportunity_ids: list[str]
    avg_confidence: float
    first_seen: str
    synthesis: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class WarRoomEngine:
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

    async def detect_convergences(self, hours: int = 4) -> list[ConvergenceSignal]:
        """Find symbols where 2+ agents agree on direction within the time window."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        cursor = await self._db.execute(
            "SELECT id, agent_name, symbol, signal, confidence, created_at, reasoning "
            "FROM opportunities "
            "WHERE created_at > ? AND status IN ('pending', 'approved', 'executed') "
            "ORDER BY created_at DESC",
            (cutoff,),
        )
        rows = await cursor.fetchall()

        # Group by (symbol, direction)
        groups: dict[tuple[str, str], list[dict]] = {}
        for r in rows:
            signal = (r[3] or "").upper()
            # Normalize signal to BUY/SELL direction
            if signal in ("BUY", "LONG", "BULLISH"):
                direction = "BUY"
            elif signal in ("SELL", "SHORT", "BEARISH"):
                direction = "SELL"
            else:
                continue

            key = (r[2], direction)  # (symbol, direction)
            if key not in groups:
                groups[key] = []
            groups[key].append({
                "id": r[0],
                "agent_name": r[1],
                "confidence": r[4] or 0.0,
                "created_at": r[5],
            })

        convergences = []
        for (symbol, direction), opps in groups.items():
            # We want unique agents
            agent_names = list({o["agent_name"] for o in opps})
            if len(agent_names) < 2:
                continue

            # Sort by creation time
            opps.sort(key=lambda x: x["created_at"])
            
            # Generate deterministic ID
            hash_in = f"{symbol}:{direction}:{opps[0]['created_at']}".encode()
            conv_id = hashlib.md5(hash_in).hexdigest()[:12]

            avg_conf = sum(o["confidence"] for o in opps) / len(opps)

            convergences.append(
                ConvergenceSignal(
                    id=conv_id,
                    symbol=symbol,
                    direction=direction,
                    agents=agent_names,
                    opportunity_ids=[o["id"] for o in opps],
                    avg_confidence=avg_conf,
                    first_seen=opps[0]["created_at"],
                )
            )

        return sorted(convergences, key=lambda c: c.first_seen, reverse=True)

    async def get_synthesis(self, convergence_id: str, hours: int = 4) -> str | None:
        """Get or generate combined reasoning for a convergence."""
        cached = await self._db.execute(
            "SELECT synthesis_text FROM convergence_syntheses WHERE convergence_id = ?",
            (convergence_id,),
        )
        cached_row = await cached.fetchone()
        if cached_row:
            return cached_row[0]

        # Find the signal
        signals = await self.detect_convergences(hours=hours)
        signal = next((s for s in signals if s.id == convergence_id), None)
        if not signal:
            return None

        # Fetch full reasoning for each opportunity
        placeholders = ",".join("?" * len(signal.opportunity_ids))
        cursor = await self._db.execute(
            f"SELECT agent_name, signal, reasoning, confidence FROM opportunities "
            f"WHERE id IN ({placeholders})",
            signal.opportunity_ids,
        )
        opps = await cursor.fetchall()

        agent_reasoning = "\n\n".join(
            f"Agent: {o[0]}\nSignal: {o[1]}\nConfidence: {o[3]:.0%}\nReasoning: {o[2]}"
            for o in opps
        )

        prompt = SYNTHESIS_PROMPT.format(
            symbol=signal.symbol,
            direction=signal.direction,
            agent_reasoning=agent_reasoning,
        )

        try:
            result = await self._llm.complete(prompt, max_tokens=300)
            if result.text:
                await self._db.execute(
                    "INSERT OR REPLACE INTO convergence_syntheses (convergence_id, synthesis_text, created_at) "
                    "VALUES (?, ?, ?)",
                    (convergence_id, result.text, datetime.utcnow().isoformat()),
                )
                await self._db.commit()
                return result.text
        except Exception as e:
            logger.warning("War Room LLM synthesis failed: %s", e)

        return None

    async def get_timeline(self, hours: int = 24) -> list[dict]:
        """Return all recent opportunities as a timeline."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        cursor = await self._db.execute(
            "SELECT id, agent_name, symbol, signal, confidence, status, created_at "
            "FROM opportunities WHERE created_at > ? ORDER BY created_at DESC",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "agent_name": r[1], "symbol": r[2],
                "signal": r[3], "confidence": r[4], "status": r[5],
                "timestamp": r[6],
            }
            for r in rows
        ]
