"""Tests for MaxCorrelation risk rule and correlation utilities."""

from __future__ import annotations

from decimal import Decimal

import pytest

from broker.models import AccountBalance, OrderBase, Quote, Symbol
from risk.correlation import avg_portfolio_correlation, pearson_correlation
from risk.rules import MaxCorrelation, PortfolioContext, RiskResult


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


class TestPearsonCorrelation:
    def test_identical_series_returns_1(self):
        x = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
        y = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
        corr = pearson_correlation(x, y)
        assert abs(corr - 1.0) < 0.001

    def test_opposite_series_returns_negative_1(self):
        x = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
        y = [Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1")]
        corr = pearson_correlation(x, y)
        assert abs(corr - (-1.0)) < 0.001

    def test_unrelated_series_returns_near_0(self):
        x = [Decimal("1"), Decimal("2"), Decimal("1"), Decimal("2")]
        y = [Decimal("1"), Decimal("1"), Decimal("2"), Decimal("2")]
        corr = pearson_correlation(x, y)
        assert abs(corr) < 0.1

    def test_short_series_returns_0(self):
        x = [Decimal("1")]
        y = [Decimal("2")]
        corr = pearson_correlation(x, y)
        assert corr == 0.0

    def test_different_lengths_returns_0(self):
        x = [Decimal("1"), Decimal("2")]
        y = [Decimal("1"), Decimal("2"), Decimal("3")]
        corr = pearson_correlation(x, y)
        assert corr == 0.0


class TestAvgPortfolioCorrelation:
    def test_single_ticker_returns_0(self):
        histories = {"SPY": [Decimal("100"), Decimal("101"), Decimal("102")]}
        avg_corr = avg_portfolio_correlation(histories)
        assert avg_corr == 0.0

    def test_two_correlated_tickers(self):
        histories = {
            "SPY": [Decimal("100"), Decimal("102"), Decimal("104"), Decimal("106")],
            "QQQ": [Decimal("200"), Decimal("204"), Decimal("208"), Decimal("212")],
        }
        avg_corr = avg_portfolio_correlation(histories)
        assert abs(avg_corr - 1.0) < 0.001

    def test_three_tickers_mixed_correlation(self):
        histories = {
            "A": [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")],
            "B": [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")],
            "C": [Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1")],
        }
        avg_corr = avg_portfolio_correlation(histories)
        # A-B: 1.0, A-C: -1.0, B-C: -1.0 => avg = -0.33
        assert -0.5 < avg_corr < 0.0


class TestMaxCorrelation:
    def test_passes_with_no_histories(self, sample_trade, sample_quote, sample_ctx):
        rule = MaxCorrelation(max_avg=0.7)
        result = rule.evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is True

    def test_passes_with_insufficient_tickers(
        self, sample_trade, sample_quote, sample_ctx
    ):
        sample_ctx.price_histories = {
            "SPY": [Decimal("100"), Decimal("101"), Decimal("102")]
        }
        rule = MaxCorrelation(max_avg=0.7)
        result = rule.evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is True

    def test_blocks_high_correlation(self, sample_trade, sample_quote, sample_ctx):
        sample_ctx.price_histories = {
            "SPY": [Decimal("100"), Decimal("102"), Decimal("104"), Decimal("106")],
            "QQQ": [Decimal("200"), Decimal("204"), Decimal("208"), Decimal("212")],
        }
        rule = MaxCorrelation(max_avg=0.5)
        result = rule.evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is False
        assert "correlation" in result.reason.lower()

    def test_passes_low_correlation(self, sample_trade, sample_quote, sample_ctx):
        sample_ctx.price_histories = {
            "A": [Decimal("1"), Decimal("2"), Decimal("1"), Decimal("2")],
            "B": [Decimal("1"), Decimal("1"), Decimal("2"), Decimal("2")],
        }
        rule = MaxCorrelation(max_avg=0.9)
        result = rule.evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is True
