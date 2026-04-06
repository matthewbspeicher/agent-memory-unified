from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from analytics.models import (
    ExitReasonBreakdown,
    RollingPoint,
    StrategySummary,
    SymbolBreakdown,
)
from learning.confidence_calibration import assign_bucket
from learning.pnl import TradeTracker

ZERO = Decimal("0")

_SIDE_NORMALIZE = {"long": "buy", "short": "sell"}


# ---------------------------------------------------------------------------
# Derivation: closed position → analytics row
# ---------------------------------------------------------------------------


def derive_analytics_row(
    position: dict[str, Any],
    opportunity: dict[str, Any] | None = None,
    execution_fills: list[dict[str, Any]] | None = None,
    signal_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert a closed tracked_position + optional metadata into a trade_analytics row."""
    side = position["side"]
    normalized_side = _SIDE_NORMALIZE.get(side.lower(), side.lower())

    entry_price = Decimal(position["entry_price"])
    exit_price = Decimal(position["exit_price"])
    quantity = Decimal(str(position["entry_quantity"]))
    entry_fees = Decimal(position.get("entry_fees") or "0")
    exit_fees = Decimal(position.get("exit_fees") or "0")

    pnl = TradeTracker.compute_pnl(
        side=normalized_side,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        entry_fees=entry_fees,
        exit_fees=exit_fees,
    )
    gross_pnl = pnl["gross_pnl"]
    net_pnl = pnl["net_pnl"]
    cost_basis = entry_price * quantity

    gross_return_pct = float(gross_pnl / cost_basis) if cost_basis else 0.0
    net_return_pct = pnl["return_pct"]

    if net_pnl > 0:
        realized_outcome = "win"
    elif net_pnl < 0:
        realized_outcome = "loss"
    else:
        realized_outcome = "flat"

    entry_time_str = position["entry_time"]
    exit_time_str = position["exit_time"]
    try:
        entry_dt = datetime.fromisoformat(entry_time_str)
        exit_dt = datetime.fromisoformat(exit_time_str)
        hold_minutes = (exit_dt - entry_dt).total_seconds() / 60.0
    except (ValueError, TypeError):
        hold_minutes = 0.0

    slippage_bps = None
    if execution_fills:
        valid = [
            f["slippage_bps"]
            for f in execution_fills
            if f.get("slippage_bps") is not None
        ]
        if valid:
            slippage_bps = sum(valid) / len(valid)

    confidence = None
    signal = None
    opp_payload: dict[str, Any] = {}
    regime_data: dict = {}
    if opportunity:
        confidence = opportunity.get("confidence")
        signal = opportunity.get("signal")
        opp_data = opportunity.get("data")
        if isinstance(opp_data, str):
            import json

            try:
                opp_data = json.loads(opp_data)
                opp_payload = opp_data if isinstance(opp_data, dict) else {}
                regime_data = (
                    opp_data.get("regime", {}) if isinstance(opp_data, dict) else {}
                )
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(opp_data, dict):
            opp_payload = opp_data
            regime_data = opp_data.get("regime", {})

    confidence_bucket = assign_bucket(confidence) if confidence is not None else None
    strategy_version = opp_payload.get("strategy_version")
    entry_spread_bps = None
    order_type = None
    suggested_trade = opportunity.get("suggested_trade") if opportunity else None
    if isinstance(suggested_trade, str):
        try:
            import json

            suggested_trade = json.loads(suggested_trade)
        except (json.JSONDecodeError, TypeError):
            suggested_trade = None
    if isinstance(suggested_trade, dict):
        if (
            suggested_trade.get("limit_price") is not None
            and suggested_trade.get("stop_price") is not None
        ):
            order_type = "stop_limit"
        elif suggested_trade.get("limit_price") is not None:
            order_type = "limit"
        elif suggested_trade.get("stop_price") is not None:
            order_type = "stop"
        else:
            order_type = "market"
    if signal_features:
        sf_confidence = signal_features.get("confidence")
        confidence_bucket = assign_bucket(
            sf_confidence if sf_confidence is not None else confidence
        )
        strategy_version = signal_features.get("feature_version")
        entry_spread_bps = signal_features.get("spread_bps")
        payload = signal_features.get("feature_payload")
        if isinstance(payload, dict):
            order_type = payload.get("order_type")

    now_str = datetime.now(timezone.utc).isoformat()

    return {
        "tracked_position_id": position["id"],
        "opportunity_id": position.get("opportunity_id"),
        "agent_name": position["agent_name"],
        "signal": signal,
        "symbol": position["symbol"],
        "side": position["side"],
        "broker_id": position.get("broker_id"),
        "account_id": position.get("account_id"),
        "entry_time": entry_time_str,
        "exit_time": exit_time_str,
        "hold_minutes": hold_minutes,
        "entry_price": str(entry_price),
        "exit_price": str(exit_price),
        "entry_quantity": int(quantity),
        "entry_fees": str(entry_fees),
        "exit_fees": str(exit_fees),
        "gross_pnl": str(gross_pnl),
        "net_pnl": str(net_pnl),
        "gross_return_pct": gross_return_pct,
        "net_return_pct": net_return_pct,
        "realized_outcome": realized_outcome,
        "exit_reason": position.get("exit_reason"),
        "confidence": confidence,
        "confidence_bucket": confidence_bucket,
        "strategy_version": strategy_version,
        "regime_label": regime_data.get("market_state"),
        "trend_regime": regime_data.get("trend_regime"),
        "volatility_regime": regime_data.get("volatility_regime"),
        "liquidity_regime": regime_data.get("liquidity_regime"),
        "execution_slippage_bps": slippage_bps,
        "entry_spread_bps": entry_spread_bps,
        "order_type": order_type,
        "created_at": now_str,
        "updated_at": now_str,
    }


def compute_summary(trades: list[dict]) -> StrategySummary:
    """Compute a StrategySummary from a list of trade_analytics rows."""
    if not trades:
        return StrategySummary(agent_name="")

    sorted_trades = sorted(trades, key=lambda t: t["exit_time"])

    agent_name = sorted_trades[0]["agent_name"]
    trade_count = len(sorted_trades)

    win_count = sum(1 for t in sorted_trades if t["realized_outcome"] == "win")
    loss_count = sum(1 for t in sorted_trades if t["realized_outcome"] == "loss")
    flat_count = sum(1 for t in sorted_trades if t["realized_outcome"] == "flat")

    win_rate = Decimal(win_count) / Decimal(trade_count) if trade_count else ZERO
    loss_rate = Decimal(loss_count) / Decimal(trade_count) if trade_count else ZERO

    gross_pnls = [Decimal(t["gross_pnl"]) for t in sorted_trades]
    net_pnls = [Decimal(t["net_pnl"]) for t in sorted_trades]

    gross_pnl = sum(gross_pnls, ZERO)
    net_pnl = sum(net_pnls, ZERO)

    avg_gross_pnl = gross_pnl / trade_count if trade_count else ZERO
    avg_net_pnl = net_pnl / trade_count if trade_count else ZERO

    win_pnls = [
        Decimal(t["net_pnl"]) for t in sorted_trades if t["realized_outcome"] == "win"
    ]
    loss_pnls = [
        Decimal(t["net_pnl"]) for t in sorted_trades if t["realized_outcome"] == "loss"
    ]

    avg_win = sum(win_pnls, ZERO) / len(win_pnls) if win_pnls else ZERO
    avg_loss = sum(loss_pnls, ZERO) / len(loss_pnls) if loss_pnls else ZERO

    expectancy = win_rate * avg_win + loss_rate * avg_loss

    if not loss_pnls:
        profit_factor = None
    elif not win_pnls:
        profit_factor = 0.0
    else:
        sum_wins = sum(win_pnls, ZERO)
        sum_losses = abs(sum(loss_pnls, ZERO))
        profit_factor = float(sum_wins / sum_losses) if sum_losses else None

    hold_minutes_list = [float(t["hold_minutes"]) for t in sorted_trades]
    avg_hold = (
        sum(hold_minutes_list) / len(hold_minutes_list) if hold_minutes_list else 0.0
    )
    median_hold = statistics.median(hold_minutes_list) if hold_minutes_list else 0.0

    best_trade = max(net_pnls)
    worst_trade = min(net_pnls)

    # Max drawdown: peak-to-trough on cumulative net PnL curve
    cumulative = ZERO
    peak = ZERO
    max_dd = ZERO
    for t in sorted_trades:
        cumulative += Decimal(t["net_pnl"])
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    return StrategySummary(
        agent_name=agent_name,
        trade_count=trade_count,
        win_count=win_count,
        loss_count=loss_count,
        flat_count=flat_count,
        win_rate=float(win_rate),
        gross_pnl=str(gross_pnl),
        net_pnl=str(net_pnl),
        avg_gross_pnl=str(avg_gross_pnl),
        avg_net_pnl=str(avg_net_pnl),
        avg_win=str(avg_win),
        avg_loss=str(avg_loss),
        expectancy=str(expectancy),
        profit_factor=profit_factor,
        avg_hold_minutes=avg_hold,
        median_hold_minutes=median_hold,
        best_trade=str(best_trade),
        worst_trade=str(worst_trade),
        max_drawdown=str(-max_dd),
    )


def compute_equity_curve(trades: list[dict], cap: int = 500) -> list[RollingPoint]:
    """Compute cumulative net PnL curve from trades ordered by exit_time ASC."""
    sorted_trades = sorted(trades, key=lambda t: t["exit_time"])
    points: list[RollingPoint] = []
    cumulative = ZERO
    for t in sorted_trades:
        cumulative += Decimal(t["net_pnl"])
        points.append(
            RollingPoint(exit_time=t["exit_time"], cumulative_net_pnl=str(cumulative))
        )
    # Down-sample if over cap
    if len(points) > cap:
        step = len(points) / cap
        sampled = [points[int(i * step)] for i in range(cap - 1)]
        sampled.append(points[-1])
        return sampled
    return points


def compute_rolling_expectancy(
    trades: list[dict], window: int = 20
) -> list[RollingPoint]:
    """Compute rolling expectancy over a sliding window of N trades."""
    sorted_trades = sorted(trades, key=lambda t: t["exit_time"])
    points: list[RollingPoint] = []
    for i in range(window, len(sorted_trades) + 1):
        window_trades = sorted_trades[i - window : i]
        w_count = len(window_trades)
        wins = [
            Decimal(t["net_pnl"])
            for t in window_trades
            if t["realized_outcome"] == "win"
        ]
        losses = [
            Decimal(t["net_pnl"])
            for t in window_trades
            if t["realized_outcome"] == "loss"
        ]
        win_rate = Decimal(len(wins)) / Decimal(w_count)
        loss_rate = Decimal(len(losses)) / Decimal(w_count)
        avg_win = sum(wins, ZERO) / len(wins) if wins else ZERO
        avg_loss = sum(losses, ZERO) / len(losses) if losses else ZERO
        exp = win_rate * avg_win + loss_rate * avg_loss

        # Cumulative net PnL up to trade i
        cum = sum((Decimal(t["net_pnl"]) for t in sorted_trades[:i]), ZERO)
        t = sorted_trades[i - 1]
        points.append(
            RollingPoint(
                exit_time=t["exit_time"],
                cumulative_net_pnl=str(cum),
                rolling_expectancy=str(exp),
            )
        )
    return points


def compute_symbol_breakdown(trades: list[dict]) -> list[SymbolBreakdown]:
    """Group trades by symbol and compute per-symbol metrics."""
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_symbol[t["symbol"]].append(t)

    results: list[SymbolBreakdown] = []
    for symbol, group in sorted(by_symbol.items()):
        count = len(group)
        wins = [t for t in group if t["realized_outcome"] == "win"]
        losses = [t for t in group if t["realized_outcome"] == "loss"]
        wr = len(wins) / count if count else 0.0
        net = sum((Decimal(t["net_pnl"]) for t in group), ZERO)
        avg_net = net / count if count else ZERO

        win_rate_d = Decimal(len(wins)) / Decimal(count) if count else ZERO
        loss_rate_d = Decimal(len(losses)) / Decimal(count) if count else ZERO
        avg_win = (
            sum((Decimal(t["net_pnl"]) for t in wins), ZERO) / len(wins)
            if wins
            else ZERO
        )
        avg_loss = (
            sum((Decimal(t["net_pnl"]) for t in losses), ZERO) / len(losses)
            if losses
            else ZERO
        )
        exp = win_rate_d * avg_win + loss_rate_d * avg_loss

        results.append(
            SymbolBreakdown(
                symbol=symbol,
                trade_count=count,
                win_rate=wr,
                net_pnl=str(net),
                avg_net_pnl=str(avg_net),
                expectancy=str(exp),
            )
        )
    return results


def compute_exit_reason_breakdown(trades: list[dict]) -> list[ExitReasonBreakdown]:
    """Group trades by exit_reason and compute per-reason metrics."""
    by_reason: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_reason[t["exit_reason"]].append(t)

    results: list[ExitReasonBreakdown] = []
    for reason, group in sorted(by_reason.items()):
        count = len(group)
        wins = [t for t in group if t["realized_outcome"] == "win"]
        wr = len(wins) / count if count else 0.0
        net = sum((Decimal(t["net_pnl"]) for t in group), ZERO)
        results.append(
            ExitReasonBreakdown(
                exit_reason=reason,
                trade_count=count,
                win_rate=wr,
                net_pnl=str(net),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Backfill: derive analytics rows from all closed tracked positions
# ---------------------------------------------------------------------------


async def backfill_analytics(
    position_store,
    analytics_store,
    opportunity_store=None,
    execution_quality_store=None,
    signal_feature_store=None,
) -> dict[str, int]:
    """Derive analytics rows from all closed tracked positions.

    Returns a dict with counts: ``{"processed": N, "skipped": N}``.
    Uses upsert so it is idempotent for re-runs.
    """
    import logging

    log = logging.getLogger(__name__)
    closed = await position_store.list_closed(limit=100_000)
    processed = 0
    skipped = 0

    for pos in closed:
        if pos.get("exit_price") is None:
            skipped += 1
            continue

        opp = None
        if opportunity_store and pos.get("opportunity_id"):
            try:
                opp = await opportunity_store.get(pos["opportunity_id"])
            except Exception:
                pass

        fills = None
        if execution_quality_store and pos.get("opportunity_id"):
            try:
                fills = await execution_quality_store.get_fills_for_agent(
                    pos["agent_name"], limit=50
                )
                fills = [
                    f for f in fills if f.get("opportunity_id") == pos["opportunity_id"]
                ]
            except Exception:
                pass

        signal_features = None
        if signal_feature_store and pos.get("opportunity_id"):
            try:
                signal_features = await signal_feature_store.get(pos["opportunity_id"])
            except Exception:
                pass

        row = derive_analytics_row(
            pos,
            opportunity=opp,
            execution_fills=fills,
            signal_features=signal_features,
        )
        await analytics_store.upsert(**row)
        processed += 1

    log.info("Backfill complete: %d processed, %d skipped", processed, skipped)
    return {"processed": processed, "skipped": skipped}


async def derive_and_upsert_for_position(
    position_id: int,
    position_store,
    analytics_store,
    opportunity_store=None,
    execution_quality_store=None,
    signal_feature_store=None,
) -> None:
    """Derive and upsert a single analytics row for a closed position.

    Intended to be called via ``asyncio.create_task()`` after ``record_exit()``.
    Failures are logged but never propagated.
    """
    import logging

    log = logging.getLogger(__name__)
    try:
        pos = await position_store.get(position_id)
        if not pos or pos.get("exit_price") is None:
            return

        opp = None
        if opportunity_store and pos.get("opportunity_id"):
            try:
                opp = await opportunity_store.get(pos["opportunity_id"])
            except Exception:
                pass

        fills = None
        if execution_quality_store and pos.get("opportunity_id"):
            try:
                fills = await execution_quality_store.get_fills_for_agent(
                    pos["agent_name"], limit=50
                )
                fills = [
                    f for f in fills if f.get("opportunity_id") == pos["opportunity_id"]
                ]
            except Exception:
                pass

        signal_features = None
        if signal_feature_store and pos.get("opportunity_id"):
            try:
                signal_features = await signal_feature_store.get(pos["opportunity_id"])
            except Exception:
                pass

        row = derive_analytics_row(
            pos,
            opportunity=opp,
            execution_fills=fills,
            signal_features=signal_features,
        )
        await analytics_store.upsert(**row)
    except Exception:
        log.exception("Failed to derive analytics for position %s", position_id)
