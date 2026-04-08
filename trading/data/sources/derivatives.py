# trading/data/sources/derivatives.py
"""Funding rate + open interest data source."""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FundingOISnapshot:
    symbol: str
    exchange: str
    funding_rate: float
    annualized_rate: float
    open_interest: float
    oi_change_24h: float

    @property
    def crowdedness_score(self) -> float:
        if self.open_interest <= 0:
            return 0.0
        return self.annualized_rate * math.log(self.open_interest)


class DerivativesDataSource:
    """Processes exchange data into funding rate snapshots."""

    def snapshot_from_fetch(
        self,
        symbol: str,
        exchange: str,
        fetch_result: Any,
    ) -> FundingOISnapshot | None:
        funding = fetch_result.funding
        if funding is None:
            return None

        rate = funding.get("rate", 0.0)
        annualized = funding.get("annualized", rate * 3 * 365)
        oi = fetch_result.oi or 0.0

        return FundingOISnapshot(
            symbol=symbol,
            exchange=exchange,
            funding_rate=rate,
            annualized_rate=annualized,
            open_interest=oi,
            oi_change_24h=0.0,  # Requires historical tracking
        )
