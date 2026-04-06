"""TradeReflector — writes trade memories and triggers deep reflection."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from learning.trade_memory import ClosedTrade

logger = logging.getLogger(__name__)


class TradeReflector:
    """Core memory service.  Injected into each agent by AgentRunner.

    reflect()       — called by ExitManager / OpportunityRouter after every close.
    query()         — called by agents before scoring an Opportunity.
    """

    def __init__(
        self,
        memory_client: Any,  # TradingMemoryClient
        deep_reflection_pnl_multiplier: float = 2.0,
        deep_reflection_loss_multiplier: float = 1.5,
        llm: Any = None,  # LLMClient | None
    ) -> None:
        self._client = memory_client
        self._pnl_mult = deep_reflection_pnl_multiplier
        self._loss_mult = deep_reflection_loss_multiplier
        if llm is not None:
            self._llm = llm
        else:
            from llm.client import LLMClient as _LLMClient

            self._llm = _LLMClient()

    async def reflect(self, trade: ClosedTrade, agent_name: str) -> None:
        """Always writes lightweight memory; conditionally triggers deep reflection."""
        await self._reflect_lightweight(trade, agent_name)
        if self._should_deep_reflect(trade):
            try:
                await self._reflect_deep(trade, agent_name)
            except Exception as e:
                logger.warning("Deep reflection failed for %s: %s", agent_name, e)

    def _should_deep_reflect(self, trade: ClosedTrade) -> bool:
        """Return True when abs(pnl) > pnl_mult × expected OR loss > loss_mult × stop."""
        tm = trade.trade_memory
        pnl_trigger = (
            abs(tm.pnl) > Decimal(str(self._pnl_mult)) * abs(trade.expected_pnl)
            if trade.expected_pnl
            else False
        )
        loss_trigger = (
            tm.outcome == "loss"
            and trade.stop_loss < 0
            and tm.pnl < Decimal(str(self._loss_mult)) * trade.stop_loss
        )
        return pnl_trigger or loss_trigger

    async def _reflect_lightweight(self, trade: ClosedTrade, agent_name: str) -> None:
        """Record trade executions in the Remembr Trading Vertical ledger."""
        tm = trade.trade_memory

        # 1. Record the Entry
        try:
            entry_resp = await self._client.record_trade(
                ticker=tm.symbol,
                direction=tm.direction,
                price=float(tm.entry_price),
                quantity=1.0,  # TODO: extract actual quantity from TradeMemory if added
                timestamp=tm.timestamp,  # Spec uses entry_at
                strategy=None,
                confidence=tm.signal_strength,
                paper=True,
                metadata={"opportunity_id": trade.opportunity_id},
            )
            parent_id = entry_resp.get("id")

            # 2. Record the Exit (linking to the entry)
            if parent_id:
                exit_direction = "short" if tm.direction == "long" else "long"
                if tm.direction in ["yes", "no"]:
                    exit_direction = "no" if tm.direction == "yes" else "yes"

                await self._client.record_trade(
                    ticker=tm.symbol,
                    direction=exit_direction,
                    price=float(tm.exit_price),
                    quantity=1.0,
                    timestamp=None,  # current time
                    parent_trade_id=parent_id,
                    fees=float(tm.slippage_bps) / 100.0,  # approximate
                    paper=True,
                )
        except Exception as e:
            logger.warning("Failed to record ledger trades for %s: %s", agent_name, e)

        # Still store the JSON legacy memory for backward compatibility/search
        payload = {
            "symbol": tm.symbol,
            "direction": tm.direction,
            "entry_price": str(tm.entry_price),
            "exit_price": str(tm.exit_price),
            "pnl": str(tm.pnl),
            "outcome": tm.outcome,
            "opportunity_id": trade.opportunity_id,
        }
        await self._client.store_private(
            content=json.dumps(payload), tags=[tm.symbol, agent_name, tm.outcome]
        )

    async def _reflect_deep(self, trade: ClosedTrade, agent_name: str) -> None:
        """Claude haiku writes a narrative lesson; extracts market observations."""
        tm = trade.trade_memory
        regime = (
            trade.trade_memory.data.get("regime", {})
            if hasattr(trade.trade_memory, "data")
            else {}
        )
        regime_str = f"Regime: {regime.get('market_phase', 'unknown')} | Volatility: {regime.get('volatility', 'unknown')}"

        prompt = (
            f"You are a trading mentor reviewing a significant trade outcome.\n\n"
            f"Agent: {agent_name} | {regime_str}\n"
            f"Symbol: {tm.symbol} | Direction: {tm.direction}\n"
            f"Entry: {tm.entry_price} | Exit: {tm.exit_price} | P&L: {tm.pnl}\n"
            f"Signal strength: {tm.signal_strength} | Hold: {tm.hold_duration_mins} min\n"
            f"Outcome: {tm.outcome} | Slippage: {tm.slippage_bps} bps\n\n"
            f"Write a structured reflection with these sections:\n"
            f"What happened: <one sentence summary of price action>\n"
            f"What triggered the signal: <one sentence technical/fundamental reason>\n"
            f"What worked: <if win, else 'N/A'>\n"
            f"What I would do differently: <specific adjustment to parameters or timing>\n"
            f"Market conditions: <regime, sector context, relevant news if known>\n"
            f"Key lesson: <one high-level takeaway for this agent>\n"
            f"Market observation: <one FACTUAL, reusable insight for ALL agents, e.g., 'AAPL liquidity dries up 10m before close' or 'Volatility spikes in this regime often lead to false breakouts'>\n\n"
            f"Respond in plain text following exactly those section headers."
        )

        try:
            result = await self._llm.complete(prompt, max_tokens=512)
            narrative = result.text or "No reflection generated."
        except Exception as e:
            logger.warning("Deep reflection LLM call failed: %s", e)
            return

        # Store full narrative in private namespace
        tags = [tm.symbol, agent_name, tm.outcome, "deep_reflection"]
        await self._client.store_private(content=narrative, tags=tags)

        # Extract market observation line and push to shared namespace
        for line in narrative.splitlines():
            if line.startswith("Market observation"):
                observation = line.split(":", 1)[-1].strip()
                if observation and observation.lower() != "none":
                    await self._client.store_shared(
                        content=observation,
                        tags=[tm.symbol, "market_observation"],
                    )
                break

    async def query(
        self, symbol: str, context: str, agent_name: str, top_k: int = 5
    ) -> list[dict]:
        """Search private + shared namespaces for relevant past memories."""
        query_text = f"{symbol} {context}"
        try:
            return await self._client.search_both(query_text, top_k=top_k)
        except Exception as e:
            logger.warning("Memory query failed for %s: %s", agent_name, e)
            return []
