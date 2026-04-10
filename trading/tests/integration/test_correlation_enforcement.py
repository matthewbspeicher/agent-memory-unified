"""Integration tests for Correlation Enforcement in Risk Pipeline."""

from __future__ import annotations

from decimal import Decimal

import pytest

from broker.models import AccountBalance, OrderBase, Quote, Symbol
from risk.rules import MaxCorrelation, PortfolioContext


@pytest.fixture
def sample_trade():
    return OrderBase(
        symbol=Symbol(ticker="SPY", asset_type="STOCK"),
        quantity=Decimal("10"),
        side="BUY",
        account_id="test_account",
    )


@pytest.fixture
def sample_quote():
    return Quote(
        symbol=Symbol(ticker="SPY", asset_type="STOCK"),
        last=Decimal("450.00"),
        bid=Decimal("449.90"),
        ask=Decimal("450.10"),
    )


@pytest.fixture
def sample_ctx():
    return PortfolioContext(
        positions=[],
        balance=AccountBalance(
            account_id="test_account",
            net_liquidation=Decimal("100000"),
            buying_power=Decimal("200000"),
            cash=Decimal("50000"),
            maintenance_margin=Decimal("0"),
        ),
    )


class TestCorrelationEnforcementIntegration:
    """Integration tests for correlation enforcement in risk pipeline."""

    @pytest.mark.asyncio
    async def test_passes_with_no_price_histories(
        self, sample_trade, sample_quote, sample_ctx
    ):
        """Test that trades pass when no price histories are available."""
        rule = MaxCorrelation(max_avg=0.7)

        result = rule.evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_passes_with_single_ticker(
        self, sample_trade, sample_quote, sample_ctx
    ):
        """Test that trades pass when only one ticker has history."""
        sample_ctx.price_histories = {
            "SPY": [Decimal("100"), Decimal("101"), Decimal("102")],
        }

        rule = MaxCorrelation(max_avg=0.7)
        result = rule.evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_blocks_high_correlation(
        self, sample_trade, sample_quote, sample_ctx
    ):
        """Test that trades are blocked when correlation exceeds threshold."""
        # Perfectly correlated series
        sample_ctx.price_histories = {
            "SPY": [Decimal("100"), Decimal("102"), Decimal("104"), Decimal("106")],
            "QQQ": [Decimal("200"), Decimal("204"), Decimal("208"), Decimal("212")],
        }

        rule = MaxCorrelation(max_avg=0.5)
        result = rule.evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is False
        assert "correlation" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_passes_with_low_correlation(
        self, sample_trade, sample_quote, sample_ctx
    ):
        """Test that trades pass when correlation is below threshold."""
        # Uncorrelated series
        sample_ctx.price_histories = {
            "A": [Decimal("1"), Decimal("2"), Decimal("1"), Decimal("2")],
            "B": [Decimal("1"), Decimal("1"), Decimal("2"), Decimal("2")],
        }

        rule = MaxCorrelation(max_avg=0.9)
        result = rule.evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is True
