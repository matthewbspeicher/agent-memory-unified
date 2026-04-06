# tests/unit/test_risk/test_correlation.py
from decimal import Decimal
import pytest

from risk.correlation import pearson_correlation, avg_portfolio_correlation


def test_pearson_correlation_perfect_positive():
    x = [Decimal(i) for i in range(1, 11)]
    y = [Decimal(i * 2 + 5) for i in range(1, 11)]
    assert pearson_correlation(x, y) == pytest.approx(1.0, 0.001)


def test_pearson_correlation_perfect_negative():
    x = [Decimal(i) for i in range(1, 11)]
    y = [Decimal(-i * 3 + 10) for i in range(1, 11)]
    assert pearson_correlation(x, y) == pytest.approx(-1.0, 0.001)


def test_pearson_correlation_zero():
    # Symmetric data
    x = [Decimal("-2"), Decimal("-1"), Decimal("0"), Decimal("1"), Decimal("2")]
    y = [Decimal("4"), Decimal("1"), Decimal("0"), Decimal("1"), Decimal("4")]
    assert pearson_correlation(x, y) == pytest.approx(0.0, 0.001)


def test_pearson_correlation_edge_cases():
    assert pearson_correlation([Decimal("1")], [Decimal("1")]) == 0.0  # < 2 items
    assert (
        pearson_correlation([Decimal("1"), Decimal("2")], [Decimal("1")]) == 0.0
    )  # Mismatched length
    # Flat line
    assert (
        pearson_correlation([Decimal("1"), Decimal("2")], [Decimal("5"), Decimal("5")])
        == 0.0
    )


def test_avg_portfolio_correlation():
    h = {
        "AAPL": [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")],
        "MSFT": [
            Decimal("2"),
            Decimal("4"),
            Decimal("6"),
            Decimal("8"),
        ],  # +1 correlation to AAPL
        "XYZ": [
            Decimal("8"),
            Decimal("6"),
            Decimal("4"),
            Decimal("2"),
        ],  # -1 correlation to AAPL and MSFT
    }
    avg = avg_portfolio_correlation(h)
    # Pairs:
    # AAPL, MSFT = 1.0
    # AAPL, XYZ  = -1.0
    # MSFT, XYZ  = -1.0
    # Total = -1.0 / 3
    assert avg == pytest.approx(-1.0 / 3.0, 0.001)
