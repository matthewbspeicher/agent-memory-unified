from decimal import Decimal, ROUND_DOWN


def compute_child_pnl(
    child_entry: str | Decimal,
    parent_entry: str | Decimal,
    child_qty: str | Decimal,
    parent_qty: str | Decimal,
    parent_direction: str,
    parent_fees: str | Decimal,
    child_fees: str | Decimal,
) -> dict:
    """
    Computes PnL for a child trade based on its parent, matching PHP's bcmath logic.
    """
    child_entry = Decimal(str(child_entry))
    parent_entry = Decimal(str(parent_entry))
    child_qty = Decimal(str(child_qty))
    parent_qty = Decimal(str(parent_qty))
    parent_fees = Decimal(str(parent_fees))
    child_fees = Decimal(str(child_fees))

    EIGHT_PLACES = Decimal("0.00000000")
    FOUR_PLACES = Decimal("0.0000")

    def truncate_8(val: Decimal) -> Decimal:
        return val.quantize(EIGHT_PLACES, rounding=ROUND_DOWN)

    if parent_direction == "long":
        diff = truncate_8(child_entry - parent_entry)
        gross_pnl = truncate_8(diff * child_qty)
    else:
        diff = truncate_8(parent_entry - child_entry)
        gross_pnl = truncate_8(diff * child_qty)

    qty_ratio = truncate_8(child_qty / parent_qty)
    fee_share = truncate_8(parent_fees * qty_ratio)

    total_fees = truncate_8(fee_share + child_fees)
    net_pnl = truncate_8(gross_pnl - total_fees)

    cost_basis = truncate_8(parent_entry * child_qty)

    if cost_basis > Decimal("0"):
        ratio = truncate_8(net_pnl / cost_basis)
        pnl_percent = (ratio * Decimal("100")).quantize(
            FOUR_PLACES, rounding=ROUND_DOWN
        )
    else:
        pnl_percent = FOUR_PLACES

    return {"pnl": f"{net_pnl:0.8f}", "pnl_percent": f"{pnl_percent:0.4f}"}
