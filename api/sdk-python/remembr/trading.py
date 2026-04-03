from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from .client import RemembrClient
from .models import TradeResult, Position, TradingStats, BulkImportResult, BulkImportError

class TradingJournal:
    """Orchestrates two-phase commit trades (Memory then Trade)."""

    def __init__(self, client: RemembrClient, paper: bool = True, default_strategy: Optional[str] = None):
        self.client = client
        self.paper = paper
        self.default_strategy = default_strategy

    def execute_trade(
        self,
        ticker: str,
        direction: str,
        quantity: float,
        price: float,
        reasoning: str,
        strategy: Optional[str] = None
    ) -> TradeResult:
        """
        Execute a trade by first storing a reasoning memory.
        
        Args:
            ticker: Asset ticker (e.g. BTC/USD)
            direction: 'buy' or 'sell'
            quantity: Amount to trade
            price: Execution price
            reasoning: Why this trade is being made
            strategy: Optional strategy name
            
        Returns:
            TradeResult: The created trade record
        """
        # Phase 1: Store memory of type 'trade_decision'
        metadata = {
            "type": "trade_decision",
            "ticker": ticker,
            "direction": direction,
            "strategy": strategy or self.default_strategy
        }
        
        memory_resp = self.client.store(
            value=reasoning,
            metadata=metadata,
            tags=["trade", ticker]
        )
        
        # Extract memory_id
        memory_id = memory_resp.get("id") or memory_resp.get("data", {}).get("id")
        if not memory_id:
            raise Exception("API Error: Failed to retrieve memory_id from store() response")

        # Phase 2: Call /trading/trades
        payload = {
            "ticker": ticker,
            "direction": direction,
            "quantity": quantity,
            "price": price,
            "memory_id": memory_id,
            "paper": self.paper
        }
        
        trade_resp = self.client.post("/trading/trades", json=payload)
        return self._map_to_trade_result(trade_resp)

    def close_trade(
        self,
        parent_trade_id: str,
        price: float,
        reasoning: str,
        quantity: Optional[float] = None
    ) -> TradeResult:
        """
        Close an existing trade by linking an outcome memory.
        
        Args:
            parent_trade_id: ID of the trade being closed
            price: Exit price
            reasoning: Outcome analysis or reason for exit
            quantity: Optional quantity to close (defaults to full remaining if server supports it)
            
        Returns:
            TradeResult: The exit trade record
        """
        # Phase 1: Store outcome memory
        metadata = {
            "type": "trade_outcome",
            "parent_trade_id": parent_trade_id
        }
        
        memory_resp = self.client.store(
            value=reasoning,
            metadata=metadata,
            tags=["trade-exit"]
        )
        
        memory_id = memory_resp.get("id") or memory_resp.get("data", {}).get("id")
        if not memory_id:
            raise Exception("API Error: Failed to retrieve memory_id from store() response")

        # Phase 2: Call /trading/trades for exit
        payload = {
            "parent_trade_id": parent_trade_id,
            "price": price,
            "memory_id": memory_id,
            "paper": self.paper
        }
        if quantity:
            payload["quantity"] = quantity
            
        trade_resp = self.client.post("/trading/trades", json=payload)
        return self._map_to_trade_result(trade_resp)

    def close_all(self, parent_trade_id: str, price: float, reasoning: str) -> TradeResult:
        """
        Convenience method to close the entire remaining quantity of a trade.
        """
        # Fetch parent trade to get current quantity
        trade_data = self.client.get_path(f"/trading/trades/{parent_trade_id}")
        
        # Extract quantity from response
        inner_data = trade_data.get("data") if "data" in trade_data else trade_data
        quantity = inner_data.get("quantity")
        
        if quantity is None:
            raise Exception(f"Could not determine quantity for trade {parent_trade_id}")
            
        return self.close_trade(
            parent_trade_id=parent_trade_id,
            price=price,
            reasoning=reasoning,
            quantity=float(quantity)
        )

    def bulk_import_trades(self, trades: Union[List[Dict[str, Any]], Any]) -> BulkImportResult:
        """
        Import a batch of trades, optionally with ref linking.
        
        Args:
            trades: List of trade dictionaries or pandas DataFrame
            
        Returns:
            BulkImportResult: Success and failure stats
        """
        if hasattr(trades, "to_dict"):
            # Assume it's a pandas DataFrame
            trades_list = trades.to_dict("records")
        else:
            trades_list = trades

        payload = {
            "trades": trades_list,
            "paper": self.paper
        }
        
        resp = self.client.post("/trading/trades/bulk", json=payload)
        return self._map_to_bulk_result(resp)

    def get_open_positions(self, ticker: Optional[str] = None, paper: Optional[bool] = None) -> List[Position]:
        """
        Fetch current open positions.
        """
        params = {"paper": paper if paper is not None else self.paper}
        if ticker:
            params["ticker"] = ticker
            
        resp = self.client.get_path("/trading/positions", params=params)
        items = resp.get("data") if "data" in resp else resp
        
        return [
            Position(
                ticker=item.get("ticker"),
                quantity=float(item.get("quantity")),
                avg_entry_price=float(item.get("avg_entry_price")),
                paper=item.get("paper", params["paper"])
            )
            for item in items
        ]

    def get_portfolio_summary(self, paper: Optional[bool] = None) -> TradingStats:
        """
        Fetch portfolio performance metrics.
        """
        params = {"paper": paper if paper is not None else self.paper}
        resp = self.client.get_path("/trading/stats", params=params)
        item = resp.get("data") if "data" in resp else resp
        
        return TradingStats(
            total_trades=int(item.get("total_trades", 0)),
            win_count=int(item.get("win_count", 0)),
            loss_count=int(item.get("loss_count", 0)),
            win_rate=float(item.get("win_rate")) if item.get("win_rate") is not None else None,
            profit_factor=float(item.get("profit_factor")) if item.get("profit_factor") is not None else None,
            total_pnl=float(item.get("total_pnl", 0.0)),
            avg_pnl_percent=float(item.get("avg_pnl_percent")) if item.get("avg_pnl_percent") is not None else None,
            best_trade_pnl=float(item.get("best_trade_pnl")) if item.get("best_trade_pnl") is not None else None,
            worst_trade_pnl=float(item.get("worst_trade_pnl")) if item.get("worst_trade_pnl") is not None else None,
            sharpe_ratio=float(item.get("sharpe_ratio")) if item.get("sharpe_ratio") is not None else None,
            current_streak=int(item.get("current_streak", 0)),
            paper=item.get("paper", params["paper"])
        )

    def get_equity_curve(self, paper: Optional[bool] = None) -> list:
        """
        Fetch the time-series cumulative PnL for charting.
        """
        params = {"paper": "true" if (paper if paper is not None else self.paper) else "false"}
        resp = self.client.get_path("/trading/stats/equity-curve", params=params)
        return resp.get("data", [])

    def get_signals(self, ticker: str = None, limit: int = 50) -> list:
        """Fetch copy-trading signals from broadcasting agents."""
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        resp = self.client.get_path("/trading/signals", params=params)
        return resp.get("data", [])

    def get_risk_metrics(self, market_prices: dict = None, paper: bool = None) -> list:
        """Get risk metrics for open positions with optional market prices."""
        params = {"paper": "true" if (paper if paper is not None else self.paper) else "false"}
        if market_prices:
            for ticker, price in market_prices.items():
                params[f"market_prices[{ticker}]"] = str(price)
        resp = self.client.get_path("/trading/risk", params=params)
        return resp.get("data", [])

    def get_drawdown(self, paper: bool = None) -> dict:
        """Get max drawdown statistics."""
        p = paper if paper is not None else self.paper
        params = {"paper": "true" if p else "false"}
        resp = self.client.get_path("/trading/risk/drawdown", params=params)
        return resp.get("data", {})

    def replay_trades(self, exit_overrides: dict = None, exit_offset_pct: float = None, paper: bool = None) -> dict:
        """Replay historical trades with alternative exit prices."""
        p = paper if paper is not None else self.paper
        body = {"paper": p}
        if exit_overrides:
            body["exit_overrides"] = exit_overrides
        if exit_offset_pct is not None:
            body["exit_offset_pct"] = exit_offset_pct
        resp = self.client.post("/trading/replay", json=body)
        return resp.get("data", {})

    def export_trades(self, format: str = "json", paper: bool = None, **filters) -> any:
        """Export trades in JSON or CSV format."""
        p = paper if paper is not None else self.paper
        params = {"format": format, "paper": "true" if p else "false", **filters}
        resp = self.client.get_path("/trading/export", params=params)
        if format == "csv":
            return resp  # Raw CSV string
        return resp.get("data", [])

    def get_portfolio(self, paper: bool = None) -> dict:
        """Get multi-agent portfolio aggregation."""
        p = paper if paper is not None else self.paper
        params = {"paper": "true" if p else "false"}
        resp = self.client.get_path("/trading/portfolio", params=params)
        return resp.get("data", {})

    def create_alert(self, condition: str, ticker: str = None, threshold: float = None) -> dict:
        """Create a trade alert."""
        body = {"condition": condition}
        if ticker:
            body["ticker"] = ticker
        if threshold is not None:
            body["threshold"] = str(threshold)
        resp = self.client.post("/trading/alerts", json=body)
        return resp.get("data", {})

    def list_alerts(self) -> list:
        """List all trade alerts."""
        resp = self.client.get_path("/trading/alerts")
        return resp.get("data", [])

    def delete_alert(self, alert_id: str) -> None:
        """Delete a trade alert."""
        self.client._request("DELETE", f"/trading/alerts/{alert_id}")

    def _map_to_trade_result(self, data: Dict[str, Any]) -> TradeResult:
        """Maps API response dictionary to TradeResult dataclass."""
        item = data.get("data") if "data" in data else data
        
        created_at = item.get("created_at")
        if isinstance(created_at, str):
            try:
                # Basic ISO format handling
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                pass
                
        return TradeResult(
            id=item.get("id"),
            parent_trade_id=item.get("parent_trade_id"),
            memory_id=item.get("memory_id"),
            ticker=item.get("ticker"),
            direction=item.get("direction"),
            price=float(item.get("price")),
            quantity=float(item.get("quantity")),
            status=item.get("status"),
            parent_status=item.get("parent_status"),
            pnl=float(item.get("pnl")) if item.get("pnl") is not None else None,
            created_at=created_at
        )

    def _map_to_bulk_result(self, data: Dict[str, Any]) -> BulkImportResult:
        """Maps API response for bulk import to BulkImportResult dataclass."""
        item = data.get("data") if "data" in data else data
        errors = [
            BulkImportError(
                index=e.get("index"),
                ref=e.get("ref"),
                reason=e.get("reason")
            )
            for e in item.get("errors", [])
        ]
        
        return BulkImportResult(
            total=item.get("total", 0),
            succeeded=item.get("succeeded", 0),
            failed=item.get("failed", 0),
            errors=errors
        )
