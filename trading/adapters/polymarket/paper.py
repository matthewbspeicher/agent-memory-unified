"""
PolymarketPaperBroker — paper trading broker for binary Polymarket prediction contracts.

The behaviour is shared by every prediction venue and lives in
adapters/prediction_paper.py. This module names the venue and its account.

Account ID for this broker: "POLYMARKET_PAPER"
"""

from __future__ import annotations

from adapters.prediction_paper import (
    DEFAULT_SLIPPAGE_CENTS,
    PredictionPaperAccount,
    PredictionPaperBroker,
    PredictionPaperConnection,
    PredictionPaperMarketData,
    PredictionPaperOrderManager,
)

__all__ = ["DEFAULT_SLIPPAGE_CENTS", "POLYMARKET_PAPER_ACCOUNT_ID", "PolymarketPaperBroker"]

POLYMARKET_PAPER_ACCOUNT_ID = "POLYMARKET_PAPER"


class PolymarketPaperConnection(PredictionPaperConnection):
    venue = "Polymarket"


class PolymarketPaperAccount(PredictionPaperAccount):
    paper_account_id = POLYMARKET_PAPER_ACCOUNT_ID
    account_type = "polymarket_paper"


class PolymarketPaperMarketData(PredictionPaperMarketData):
    venue = "Polymarket"


class PolymarketPaperOrderManager(PredictionPaperOrderManager):
    venue = "Polymarket"
    paper_account_id = POLYMARKET_PAPER_ACCOUNT_ID


class PolymarketPaperBroker(PredictionPaperBroker):
    """Standalone paper broker for binary Polymarket prediction contracts."""

    venue = "Polymarket"
    connection_class = PolymarketPaperConnection
    account_class = PolymarketPaperAccount
    market_data_class = PolymarketPaperMarketData
    order_manager_class = PolymarketPaperOrderManager
