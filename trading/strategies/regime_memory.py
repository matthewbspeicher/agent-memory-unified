from __future__ import annotations
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Dict, Any

from agents.base import Agent
from agents.models import AgentConfig, Opportunity, AgentSignal
from strategies.bittensor_consensus import BittensorAlphaAgent
from memory.market_regime import RegimeMemoryManager
from adapters.remembr.client import AsyncRemembrClient

if TYPE_CHECKING:
    from data.bus import DataBus

logger = logging.getLogger(__name__)


class RegimeAwareAgent(Agent):
    """
    Enhanced BittensorAlphaAgent that uses Vector Memory to recall how
    similar market regimes performed in the past.
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self._inner = BittensorAlphaAgent(config)
        self._memory_manager: RegimeMemoryManager | None = None
        self._pending_opportunities: list[Opportunity] = []

    async def setup(self):
        await self._inner.setup()

        # Initialize Remembr client from config
        token = self.config.parameters.get("remembr_agent_token")
        base_url = self.config.parameters.get(
            "remembr_base_url", "https://remembr.dev/api/v1"
        )

        if token:
            client = AsyncRemembrClient(token, base_url=base_url)
            self._memory_manager = RegimeMemoryManager(client)
            logger.info("RegimeAwareAgent: Memory Loop active.")
        else:
            logger.warning(
                "RegimeAwareAgent: No remembr_agent_token provided. Memory Loop disabled."
            )

    @property
    def signal_bus(self):
        return self._inner.signal_bus

    @signal_bus.setter
    def signal_bus(self, bus):
        self._inner.signal_bus = bus

    async def scan(self, data: DataBus) -> list[Opportunity]:
        # 1. Get base opportunities from consensus
        base_opps = await self._inner.scan(data)
        if not base_opps or self._memory_manager is None:
            return base_opps

        final_opps = []
        for opp in base_opps:
            # 2. Enrich with Regime Memory
            symbol = opp.suggested_trade.symbol if opp.suggested_trade else None
            if not symbol:
                final_opps.append(opp)
                continue

            # Fetch recent bars for regime detection
            bars = await data.get_historical(symbol, timeframe="1h", period="5d")
            regime = self._memory_manager.detect_regime(bars)

            # 3. Recall similar past regimes
            past_memories = await self._memory_manager.recall_similar_regimes(
                symbol, regime
            )

            # 4. Adjust conviction based on memory
            # (Simple heuristic: if we have positive memories of this regime, boost confidence)
            conviction_boost = 0.0
            if past_memories:
                logger.info(
                    "Recalled %d similar regimes for %s",
                    len(past_memories),
                    symbol.ticker,
                )
                # In a real implementation, we'd parse the outcomes of those past regimes
                conviction_boost = 0.1

            opp.confidence = min(1.0, float(opp.confidence) + conviction_boost)
            opp.reasoning += f"\n- Market Regime: {regime} (Recalled {len(past_memories)} similar instances)"

            # 5. Store current regime for future learning
            # We do this asynchronously to not block scan
            metrics = {"volatility": 0.01}  # Placeholder
            import asyncio

            asyncio.create_task(
                self._memory_manager.store_regime(symbol, regime, metrics)
            )

            final_opps.append(opp)

        return final_opps
