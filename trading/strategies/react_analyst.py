"""ReACT-based analyst agent with iterative reasoning loop.

Uses Reasoning-Acting-Observing loop to build layered market
analysis by querying multiple data sources iteratively.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agents.base import LLMAgent
from agents.models import Opportunity, OpportunityStatus
from data.bus import DataBus

logger = logging.getLogger(__name__)


class ReactAnalystAgent(LLMAgent):
    def __init__(self, config, prompt_store=None, llm_client=None):
        super().__init__(config, prompt_store)
        self._llm_client = llm_client

    @property
    def model(self) -> str:
        return self._config.model or "claude-opus-4-6"

    @property
    def description(self) -> str:
        return f"ReACT analyst using {self.model} with iterative reasoning loop"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        """Scan market using ReACT reasoning loop.

        Args:
            data: DataBus for accessing market data.

        Returns:
            List of trading opportunities discovered.
        """
        symbols = data.get_universe(self.config.universe)
        if not symbols:
            return []

        opportunities = []

        for symbol in symbols[:5]:
            try:
                opp = await self._analyze_symbol(data, symbol)
                if opp:
                    opportunities.append(opp)
            except Exception as e:
                logger.warning("ReactAnalyst failed for %s: %s", symbol, e)

        return opportunities

    async def _analyze_symbol(
        self, data: DataBus, symbol: Any
    ) -> Optional[Opportunity]:
        max_iterations = self.config.parameters.get("max_iterations", 5)
        confidence_threshold = self.config.parameters.get("confidence_threshold", 0.6)

        context = await self._gather_initial_context(data, symbol)
        reasoning_trace: list[dict[str, Any]] = []
        tools_used: list[str] = []

        for iteration in range(max_iterations):
            thought = await self._generate_thought(context, reasoning_trace, tools_used)
            reasoning_trace.append({"iteration": iteration, "thought": thought})

            if self._should_conclude(thought):
                break

            action = await self._generate_action(thought, context)

            if action.get("type") == "final_answer":
                break

            observation = await self._execute_tool(data, symbol, context, action)
            tools_used.append(action.get("tool", "unknown"))
            reasoning_trace.append(
                {
                    "iteration": iteration,
                    "action": action,
                    "observation": observation,
                }
            )

        return await self._generate_opportunity(
            symbol, reasoning_trace, confidence_threshold
        )

    async def _gather_initial_context(
        self, data: DataBus, symbol: Any
    ) -> dict[str, Any]:
        """Gather initial market context for analysis.

        Args:
            data: DataBus for market data.
            symbol: Trading symbol.

        Returns:
            Dictionary with initial market context.
        """
        quote = await data.get_quote(symbol)
        rsi = await data.get_rsi(symbol, period=14)
        sma_20 = await data.get_sma(symbol, period=20)

        return {
            "symbol": str(symbol),
            "price": quote.last if quote else None,
            "volume": quote.volume if quote else None,
            "rsi": rsi,
            "sma_20": sma_20,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _generate_thought(
        self,
        context: dict[str, Any],
        trace: list[dict[str, Any]],
        tools_used: list[str],
    ) -> str:
        prompt = f"""You are a quantitative trading analyst analyzing {context["symbol"]}.

Current Market Data:
- Price: {context.get("price", "N/A")}
- Volume: {context.get("volume", "N/A")}
- RSI(14): {context.get("rsi", "N/A")}
- SMA(20): {context.get("sma_20", "N/A")}

Previous Reasoning:
{json.dumps(trace[-3:] if len(trace) > 3 else trace, indent=2)}

Tools Used: {tools_used}

Analyze the current situation and determine what you need to know next.
If you have enough information to make a trading decision, state your conclusion clearly.
Otherwise, specify what additional data would help your analysis."""

        if self._llm_client:
            self.increment_llm_call_count()
            result = await self._llm_client.chat(
                system=self.system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            return result.text

        return ""

    def _should_conclude(self, thought: str) -> bool:
        """Check if thought indicates readiness to conclude.

        Args:
            thought: Thought text to analyze.

        Returns:
            True if conclusion keywords found.
        """
        conclusion_keywords = ["conclusion", "recommendation", "signal", "opportunity"]
        return any(kw in thought.lower() for kw in conclusion_keywords)

    async def _generate_action(
        self,
        thought: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = f"""Based on this analysis:
{thought}

Available tools:
1. query_market_data - Get additional price/volume data
2. query_indicators - Get technical indicators (MACD, BB, ATR)
3. query_agent_memory - Get past trade lessons for this symbol
4. query_knowledge_graph - Get related market entities and relationships
5. final_answer - Conclude with trading decision

Respond with JSON:
{{"tool": "<tool_name>", "params": {{...}}}} or {{"type": "final_answer", "answer": "..."}}"""

        if self._llm_client:
            self.increment_llm_call_count()
            result = await self._llm_client.chat(
                system="You are a trading analyst. Respond with valid JSON only.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            try:
                return json.loads(result.text)
            except json.JSONDecodeError:
                pass

        return {"type": "final_answer"}

    async def _execute_tool(
        self,
        data: DataBus,
        symbol: Any,
        context: dict[str, Any],
        action: dict[str, Any],
    ) -> str:
        """Execute tool and return observation.

        Args:
            data: DataBus for market data.
            symbol: Trading symbol.
            action: Action dictionary.

        Returns:
            Observation string from tool execution.
        """
        tool = action.get("tool", "")

        if tool == "query_market_data":
            quote = await data.get_quote(symbol)
            return f"Price: {quote.last if quote else 'N/A'}, Volume: {quote.volume if quote else 'N/A'}"

        elif tool == "query_indicators":
            macd = await data.get_macd(symbol)
            bb = await data.get_bollinger(symbol)
            return f"MACD: {macd}, Bollinger: {bb}"

        elif tool == "query_agent_memory":
            if hasattr(self, "memory") and self.memory:
                lessons = await self.memory.query(
                    symbol, json.dumps(context), self.name, top_k=5
                )
                return f"Past lessons: {lessons}"
            return "No memory available"

        elif tool == "query_knowledge_graph":
            # Access Knowledge Graph via app.state (dependency injection needed or via DataBus)
            # For now, we assume it might be available on the agent if injected by runner
            kg = getattr(self, "knowledge_graph", None)
            if kg:
                try:
                    triples = await kg.query_entity(str(symbol), direction="both")
                    return f"KG triples for {symbol}: {triples[:10]}"
                except Exception as e:
                    return f"KG query failed: {e}"
            return "Knowledge Graph not available"

        return f"Unknown tool: {tool}"

    async def _generate_opportunity(
        self,
        symbol: Any,
        trace: list[dict[str, Any]],
        confidence_threshold: float,
    ) -> Optional[Opportunity]:
        prompt = f"""Based on this analysis trace for {symbol}:
{json.dumps(trace, indent=2)}

Generate a trading opportunity as JSON:
{{
    "signal": "<SIGNAL_TYPE>",
    "confidence": <0.0-1.0>,
    "reasoning": "<concise explanation>",
    "direction": "<bullish|bearish|neutral>"
}}

Only generate if confidence >= {confidence_threshold} and signal is clear."""

        if not self._llm_client:
            return None

        self.increment_llm_call_count()
        result = await self._llm_client.chat(
            system="You are a trading analyst. Respond with valid JSON only.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )

        try:
            data = json.loads(result.text)

            if data.get("confidence", 0) < confidence_threshold:
                return None

            if data.get("direction") == "neutral":
                return None

            return Opportunity(
                id=str(uuid.uuid4()),
                agent_name=self.name,
                symbol=symbol,
                signal=data["signal"],
                confidence=data["confidence"],
                reasoning=data["reasoning"],
                data={
                    "trace_length": len(trace),
                    "direction": data["direction"],
                },
                timestamp=datetime.now(timezone.utc),
                status=OpportunityStatus.PENDING,
            )
        except (json.JSONDecodeError, KeyError):
            return None
