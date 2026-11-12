"""
KalshiPaperBroker — paper trading broker for binary Kalshi prediction contracts.

The behaviour is shared by every prediction venue and lives in
adapters/prediction_paper.py. This module names the venue and its account.

Account ID for this broker: "KALSHI_PAPER"
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

__all__ = ["DEFAULT_SLIPPAGE_CENTS", "KALSHI_PAPER_ACCOUNT_ID", "KalshiPaperBroker"]

KALSHI_PAPER_ACCOUNT_ID = "KALSHI_PAPER"


class KalshiPaperConnection(PredictionPaperConnection):
    venue = "Kalshi"


class KalshiPaperAccount(PredictionPaperAccount):
    paper_account_id = KALSHI_PAPER_ACCOUNT_ID
    account_type = "kalshi_paper"


class KalshiPaperMarketData(PredictionPaperMarketData):
    venue = "Kalshi"


class KalshiPaperOrderManager(PredictionPaperOrderManager):
    venue = "Kalshi"
    paper_account_id = KALSHI_PAPER_ACCOUNT_ID


class KalshiPaperBroker(PredictionPaperBroker):
    """Standalone paper broker for binary Kalshi prediction contracts."""

    venue = "Kalshi"
    connection_class = KalshiPaperConnection
    account_class = KalshiPaperAccount
    market_data_class = KalshiPaperMarketData
    order_manager_class = KalshiPaperOrderManager
