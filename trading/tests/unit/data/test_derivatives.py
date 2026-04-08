# tests/unit/data/test_derivatives.py
from __future__ import annotations

import math
import pytest
from data.sources.derivatives import FundingOISnapshot, DerivativesDataSource
from data.exchange_client import FetchResult


class TestFundingOISnapshot:
    def test_crowdedness_score(self):
        snap = FundingOISnapshot(
            symbol="BTCUSD",
            exchange="binance",
            funding_rate=0.001,
            annualized_rate=0.001 * 3 * 365,
            open_interest=1_000_000_000,
            oi_change_24h=0.05,
        )
        expected = snap.annualized_rate * math.log(snap.open_interest)
        assert snap.crowdedness_score == pytest.approx(expected, abs=0.01)

    def test_zero_oi_crowdedness(self):
        snap = FundingOISnapshot(
            symbol="BTCUSD",
            exchange="binance",
            funding_rate=0.001,
            annualized_rate=1.095,
            open_interest=0,
            oi_change_24h=0,
        )
        assert snap.crowdedness_score == 0.0


class TestDerivativesDataSource:
    @pytest.mark.asyncio
    async def test_from_fetch_result(self):
        result = FetchResult(
            funding={"rate": 0.0005, "annualized": 0.0005 * 3 * 365},
            oi=500_000_000.0,
        )
        source = DerivativesDataSource()
        snap = source.snapshot_from_fetch("BTCUSD", "binance", result)
        assert snap is not None
        assert snap.funding_rate == 0.0005
        assert snap.annualized_rate == pytest.approx(0.0005 * 3 * 365)
        assert snap.open_interest == 500_000_000.0

    @pytest.mark.asyncio
    async def test_from_fetch_result_missing_funding(self):
        result = FetchResult(oi=500_000_000.0)
        source = DerivativesDataSource()
        snap = source.snapshot_from_fetch("BTCUSD", "binance", result)
        assert snap is None
