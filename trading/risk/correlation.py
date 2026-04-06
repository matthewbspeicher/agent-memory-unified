# risk/correlation.py
from decimal import Decimal


def pearson_correlation(x: list[Decimal], y: list[Decimal]) -> float:
    """
    Computes the Pearson correlation coefficient for two time series using pure Python math.
    Returns a value between -1.0 (perfect negative) and 1.0 (perfect positive).
    """
    if len(x) != len(y) or len(x) < 2:
        return 0.0

    n = len(x)
    sum_x = sum(float(v) for v in x)
    sum_y = sum(float(v) for v in y)

    sum_x_sq = sum(float(v) ** 2 for v in x)
    sum_y_sq = sum(float(v) ** 2 for v in y)

    sum_xy = sum(float(xv) * float(yv) for xv, yv in zip(x, y))

    numerator = (n * sum_xy) - (sum_x * sum_y)
    denominator_sq_x = (n * sum_x_sq) - (sum_x**2)
    denominator_sq_y = (n * sum_y_sq) - (sum_y**2)

    if denominator_sq_x <= 0 or denominator_sq_y <= 0:
        return 0.0

    denominator = (denominator_sq_x * denominator_sq_y) ** 0.5
    if denominator == 0:
        return 0.0

    return numerator / denominator


def avg_portfolio_correlation(price_histories: dict[str, list[Decimal]]) -> float:
    """
    Given a dict of ticker -> list of daily closing prices, computes the average pairwise
    Pearson correlation across all unique pairs in the portfolio.
    """
    symbols = list(price_histories.keys())
    if len(symbols) < 2:
        return 0.0

    correlations = []
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            x = price_histories[symbols[i]]
            y = price_histories[symbols[j]]
            corr = pearson_correlation(x, y)
            correlations.append(corr)

    if not correlations:
        return 0.0

    return sum(correlations) / len(correlations)
