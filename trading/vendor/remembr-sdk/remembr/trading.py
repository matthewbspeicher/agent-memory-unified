from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from decimal import Decimal

if TYPE_CHECKING:
    from .client import AsyncRemembrClient, RemembrClient

logger = logging.getLogger(__name__)

class TradingJournal:
    """
    High-level SDK component for trade journaling with semantic memory links.
    Implements two-phase commit: 1. Create Decision Memory -> 2. Execute Trade.
    """
    def __init__(self, client: AsyncRemembrClient, paper: bool = True, strategy: Optional[str] = None):
        self.client = client
        self.paper = paper
        self.default_strategy = strategy

    async def execute_trade(
        self, 
        ticker: str, 
        direction: str, 
        price: float, 
        quantity: float, 
        reasoning: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """
        Executes a trade and automatically creates a linked decision memory.
        """
        # 1. Create Decision Memory first
        metadata = {
            "type": "trade_decision",
            "ticker": ticker,
            "direction": direction,
            "price": price,
            "quantity": quantity,
            "strategy": self.default_strategy,
            **kwargs.get("metadata", {})
        }
        
        try:
            memory = await self.client.store(
                value=f"Decision to {direction} {quantity} {ticker} at {price}. Reasoning: {reasoning}",
                metadata=metadata,
                tags=["trade_decision", ticker, direction.lower()]
            )
            memory_id = memory.get("key")
            
            # 2. Execute Trade with linked memory_id (hits the stock-trading-api /trading/trades)
            # Note: This assumes the client base_url is configured to point to the trading service
            # or the remembr backend handles the trade routing.
            payload = {
                "ticker": ticker,
                "direction": direction,
                "price": price,
                "quantity": quantity,
                "reasoning_memory_id": memory_id,
                "paper": self.paper,
                **kwargs
            }
            
            # Use the underlying httpx client to post to the trading endpoint
            resp = await self.client.client.post("/trading/trades", json=payload)
            if resp.is_error:
                logger.error(f"TradingJournal: Trade execution failed: {resp.text}")
                return {"status": "error", "message": resp.text, "memory_id": memory_id}
                
            return {**resp.json(), "memory_id": memory_id}
            
        except Exception as e:
            logger.exception("TradingJournal: Fatal error in execute_trade")
            raise

    async def close_trade(self, trade_id: str, exit_price: float, pnl: float, lesson: str) -> Dict[str, Any]:
        """
        Closes a trade and updates the semantic memory with the outcome.
        """
        try:
            # 1. Update the original memory with autopsy data
            await self.client.store(
                value=f"Trade {trade_id} closed at {exit_price}. PnL: {pnl}. Lesson: {lesson}",
                key=trade_id,
                metadata={"type": "trade_outcome", "pnl": pnl, "exit_price": exit_price, "lesson": lesson},
                tags=["trade_outcome", "completed"]
            )
            
            # 2. Inform the trading backend
            resp = await self.client.client.post(f"/trading/trades/{trade_id}/close", json={
                "exit_price": exit_price,
                "pnl": pnl
            })
            return resp.json()
        except Exception as e:
            logger.error(f"TradingJournal: Failed to close trade {trade_id}: {e}")
            raise

    async def bulk_import_trades(self, data: Any) -> Dict[str, Any]:
        """
        Handles bulk import of trades from lists or DataFrames.
        """
        # Placeholder for Task 3 implementation
        logger.info("TradingJournal: Executing bulk_import_trades")
        return {"status": "success", "imported_count": 0}
