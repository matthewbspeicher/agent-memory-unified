"""Kelly criterion position sizing."""
from __future__ import annotations
from decimal import Decimal, ROUND_DOWN


def kelly_fraction(win_rate: float, avg_win: Decimal, avg_loss: Decimal) -> float:
    """Kelly f* = p - q/b. Returns 0-1 (clamped to [0, 1]).

    Computed in Decimal to avoid floating-point precision drift.
    """
    if win_rate <= 0 or avg_win <= 0:
        return 0.0
    if avg_loss <= 0:
        return min(win_rate, 1.0)
    p = Decimal(str(win_rate))
    q = Decimal("1") - p
    b = avg_win / avg_loss
    f = p - q / b
    return float(max(Decimal("0"), min(f, Decimal("1"))))


def compute_position_size(
    win_rate: float,
    avg_win: Decimal,
    avg_loss: Decimal,
    bankroll: Decimal,
    price: Decimal,
    kelly_multiplier: Decimal = Decimal("0.5"),
    max_pct: Decimal = Decimal("0.10"),
) -> Decimal:
    """Compute position size in shares using fractional Kelly.

    Returns whole shares (rounded down), capped by max_pct of bankroll.
    Returns 0 if there is no edge or price is 0.
    """
    f = kelly_fraction(win_rate, avg_win, avg_loss)
    if f <= 0 or price <= 0:
        return Decimal("0")
    frac = min(Decimal(str(f)) * kelly_multiplier, max_pct)
    return (bankroll * frac / price).to_integral_value(rounding=ROUND_DOWN)
