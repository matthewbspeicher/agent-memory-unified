"""
Daily Trade Compiler — Background worker to compile raw TradeMemory records
into structured daily summaries.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from learning.memory_client import TradingMemoryClient

if TYPE_CHECKING:
    from llm.client import LLMClient

logger = logging.getLogger(__name__)


class DailyTradeCompiler:
    def __init__(
        self,
        memory_client: TradingMemoryClient,
        llm: "LLMClient | None" = None,
        compile_hour: int = 18,
        compile_minute: int = 0,
    ) -> None:
        self._memory = memory_client
        if llm is not None:
            self._llm = llm
        else:
            from llm.client import LLMClient

            self._llm = LLMClient()
        self.compile_hour = compile_hour
        self.compile_minute = compile_minute
        self._running = False
        self._last_run_date: str | None = None

    async def compile_daily_summary(self) -> str:
        """
        Reads the day's trades and observations, uses the LLM to summarize
        lessons, and stores the compiled knowledge back into Remembr.
        """
        logger.info("Starting Daily Trade Compilation...")

        # 1. Fetch raw data
        # We search both namespaces for today's trades and deep reflections.
        raw_memories = await self._memory.search_both(
            "trade deep_reflection market_observation", top_k=50
        )

        if not raw_memories:
            logger.info("No raw memories found for compilation.")
            return "No raw memories found."

        # Filter memories that are from today based on some heuristic or just compile all retrieved
        # Assuming search gets the most relevant/recent.
        context_parts = []
        for mem in raw_memories:
            content = mem.get("value", "")
            tags = mem.get("tags", [])
            context_parts.append(f"Memory (tags: {tags}):\n{content}")

        context_text = "\n\n".join(context_parts)

        # 2. Compile using LLM
        prompt = (
            "You are a trading strategy compiler. Review the following raw trade memories "
            "and market observations from today.\n\n"
            "Raw Data:\n"
            f"{context_text}\n\n"
            "Compile this into a structured 'Daily Trade Summary' markdown document with these sections:\n"
            "## Trades Executed\n(Summary of actions)\n"
            "## Patterns Detected\n(Any recurring themes or technical setups)\n"
            "## Lessons\n(What went right or wrong)\n"
            "## Action Items\n(Adjustments for tomorrow)\n"
            "Be concise and analytical. Provide only the markdown."
        )

        try:
            result = await self._llm.complete(prompt, max_tokens=1024)
            summary = result.text or "No summary generated."
        except Exception as e:
            logger.error("LLM compilation failed: %s", e)
            return ""

        # 3. Store the compiled summary
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tags = ["daily_summary", "strategy_article", date_str]

        try:
            await self._memory.store_private(
                content=f"# Daily Summary: {date_str}\n\n{summary}",
                tags=tags,
            )
            logger.info("Daily trade summary compiled and stored successfully.")
        except Exception as e:
            logger.error("Failed to store compiled summary: %s", e)

        return summary

    async def start_loop(self) -> None:
        """Run the compiler loop, triggering at the specified hour and minute."""
        self._running = True
        logger.info(
            f"DailyTradeCompiler loop started. Will compile at {self.compile_hour:02d}:{self.compile_minute:02d} UTC."
        )
        while self._running:
            now = datetime.now(timezone.utc)
            today_str = now.strftime("%Y-%m-%d")

            # Check if it's time to compile and we haven't compiled today
            if now.hour == self.compile_hour and now.minute >= self.compile_minute:
                if self._last_run_date != today_str:
                    logger.info("Triggering scheduled daily compilation.")
                    try:
                        await self.compile_daily_summary()
                        self._last_run_date = today_str
                    except Exception as e:
                        logger.error("Error during scheduled compilation: %s", e)

            # Sleep for a bit before checking again
            await asyncio.sleep(60)

    async def handle_knowledge_capture(self, signal) -> None:
        """Handle real-time knowledge.capture signals from agents."""
        if signal.signal_type != "knowledge.capture":
            return

        content = signal.payload.get("rationale", "")
        if not content:
            return

        logger.info("Captured real-time knowledge from %s", signal.source_agent)
        try:
            await self._memory.store_shared(
                content=content,
                tags=["market_observation", "knowledge_capture", signal.source_agent],
            )
        except Exception as e:
            logger.error("Failed to store knowledge capture: %s", e)

    def stop(self) -> None:
        self._running = False
