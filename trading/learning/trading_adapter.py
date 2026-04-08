"""
TradingRemembrClient — specialized client for the Remembr Trading Vertical.
Implements the ledger-based trading journal spec (2026-03-31).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from remembr.client import AsyncRemembrClient, _handle_error

logger = logging.getLogger(__name__)


class TradingRemembrClient(AsyncRemembrClient):
    """
    Extends the standard AsyncRemembrClient with Trading Vertical endpoints.
    """

    async def record_trade(
        self,
        ticker: str,
        direction: str,
        price: float,
        quantity: float,
        timestamp: Optional[datetime] = None,
        strategy: Optional[str] = None,
        confidence: Optional[float] = None,
        paper: bool = True,
        fees: float = 0.0,
        parent_trade_id: Optional[str] = None,
        decision_memory_id: Optional[str] = None,
        outcome_memory_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Record a trade execution (entry or exit).
        POST /v1/trading/trades
        """
        payload = {
            "ticker": ticker,
            "direction": direction,
            "entry_price": float(
                price
            ),  # Spec uses entry_price for the execution price
            "quantity": float(quantity),
            "entry_at": (timestamp or datetime.utcnow()).isoformat(),
            "paper": paper,
            "fees": float(fees),
        }
        if strategy:
            payload["strategy"] = strategy
        if confidence is not None:
            payload["confidence"] = confidence
        if parent_trade_id:
            payload["parent_trade_id"] = parent_trade_id
        if decision_memory_id:
            payload["decision_memory_id"] = decision_memory_id
        if outcome_memory_id:
            payload["outcome_memory_id"] = outcome_memory_id
        if metadata:
            payload["metadata"] = metadata

        resp = await self.client.post("/trading/trades", json=payload)
        if resp.is_error:
            _handle_error(resp)
        return resp.json()

    async def update_trade_metadata(
        self,
        trade_id: str,
        decision_memory_id: Optional[str] = None,
        outcome_memory_id: Optional[str] = None,
        strategy: Optional[str] = None,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update mutable trade metadata.
        PATCH /v1/trading/trades/{id}
        """
        payload: dict[str, Any] = {}
        if decision_memory_id:
            payload["decision_memory_id"] = decision_memory_id
        if outcome_memory_id:
            payload["outcome_memory_id"] = outcome_memory_id
        if strategy:
            payload["strategy"] = strategy
        if confidence is not None:
            payload["confidence"] = confidence
        if metadata:
            payload["metadata"] = metadata
        if status:
            payload["status"] = status

        resp = await self.client.patch(f"/trading/trades/{trade_id}", json=payload)
        if resp.is_error:
            _handle_error(resp)
        return resp.json()

    async def get_trading_stats(self, paper: bool = True) -> Dict[str, Any]:
        """
        Retrieve aggregate performance stats for the agent.
        GET /v1/trading/stats
        """
        params = {"paper": str(paper).lower()}
        resp = await self.client.get("/trading/stats", params=params)
        if resp.is_error:
            _handle_error(resp)
        return resp.json()

    async def list_trades(
        self, ticker: Optional[str] = None, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List agent's trades with filters.
        GET /v1/trading/trades
        """
        params = {}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status

        resp = await self.client.get("/trading/trades", params=params)
        if resp.is_error:
            _handle_error(resp)
        return resp.json().get("data", [])

    async def get_positions(self, paper: bool = True) -> List[Dict[str, Any]]:
        """
        Retrieve current open positions.
        GET /v1/trading/positions
        """
        params = {"paper": str(paper).lower()}
        resp = await self.client.get("/trading/positions", params=params)
        if resp.is_error:
            _handle_error(resp)
        return resp.json()
