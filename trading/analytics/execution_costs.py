"""Execution cost aggregation service."""

from __future__ import annotations

import statistics
from typing import Any


def _safe_median(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.median(values)


def _safe_p95(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * 0.95) - 1)
    return sorted_vals[idx]


def compute_grouped_summary(
    rows: list[dict[str, Any]],
    group_by: str,
) -> list[dict[str, Any]]:
    """Aggregate execution cost rows into per-group summaries.

    Computes: trade_count, avg/median spread_bps, avg/median/p95 slippage_bps,
    avg_fee_dollars, rejection_rate, partial_fill_rate.

    group_by must match a key present in each row dict (e.g. 'broker_id',
    'symbol', 'agent_name', 'order_type').
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(group_by) or "unknown")
        groups.setdefault(key, []).append(row)

    results = []
    for group_key, group_rows in groups.items():
        spread_vals = [
            r["spread_bps"] for r in group_rows if r.get("spread_bps") is not None
        ]
        slip_vals = [
            r["slippage_bps"] for r in group_rows if r.get("slippage_bps") is not None
        ]
        fee_vals: list[float] = []
        for r in group_rows:
            try:
                fee_vals.append(float(r["fees_total"]))
            except (TypeError, ValueError):
                pass

        rejected = sum(1 for r in group_rows if r.get("status") == "rejected")
        partial = sum(1 for r in group_rows if r.get("status") == "partial")
        total = len(group_rows)

        results.append(
            {
                "group_key": group_key,
                "trade_count": total,
                "avg_spread_bps": (sum(spread_vals) / len(spread_vals))
                if spread_vals
                else None,
                "median_spread_bps": _safe_median(spread_vals),
                "avg_slippage_bps": (sum(slip_vals) / len(slip_vals))
                if slip_vals
                else None,
                "median_slippage_bps": _safe_median(slip_vals),
                "p95_slippage_bps": _safe_p95(slip_vals),
                "avg_fee_dollars": (sum(fee_vals) / len(fee_vals))
                if fee_vals
                else None,
                "rejection_rate": (rejected / total) if total else None,
                "partial_fill_rate": (partial / total) if total else None,
            }
        )

    results.sort(
        key=lambda r: (
            r["avg_slippage_bps"]
            if r["avg_slippage_bps"] is not None
            else float("-inf")
        ),
        reverse=True,
    )
    return results


def compute_worst_groups(
    rows: list[dict[str, Any]],
    group_by: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the worst-performing groups sorted by avg_slippage_bps descending."""
    summaries = compute_grouped_summary(rows, group_by)
    # filter out groups with no slippage data
    with_slippage = [s for s in summaries if s["avg_slippage_bps"] is not None]
    return with_slippage[:limit]
