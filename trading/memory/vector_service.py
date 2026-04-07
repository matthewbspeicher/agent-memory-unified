from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

from llm.client import LLMClient
from broker.models import Bar, Symbol

logger = logging.getLogger(__name__)

class MarketVectorService:
    """Generates and manages market context vectors."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def create_context_string(self, symbol: Symbol, bars: List[Bar], sentiment: Dict[str, Any] | None = None) -> str:
        """Create a descriptive string of the current market state for embedding."""
        if not bars:
            return f"Market context for {symbol.ticker}: No data."

        last_bar = bars[-1]
        first_bar = bars[0]
        price_change = (float(last_bar.close) - float(first_bar.open)) / float(first_bar.open)
        
        # Simple technical summary
        volatility = sum(abs(float(bars[i].close) - float(bars[i-1].close)) for i in range(1, len(bars))) / len(bars)
        
        context = (
            f"Symbol: {symbol.ticker}. "
            f"Price Change: {price_change:.2%}. "
            f"Volatility: {volatility:.4f}. "
            f"Last Price: {last_bar.close:.4f}. "
        )
        
        if sentiment:
            context += f"Sentiment Score: {sentiment.get('score', 0):.2f}. "
            
        return context

    async def vectorize_context(self, context_string: str) -> List[float]:
        """Convert a context string into a high-dimensional vector."""
        return await self.llm_client.embed(context_string)
