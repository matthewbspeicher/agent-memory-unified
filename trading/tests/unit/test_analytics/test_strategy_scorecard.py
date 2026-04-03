from __future__ import annotations

from decimal import Decimal

from analytics.models import StrategySummary
from analytics.strategy_scorecard import (
    compute_equity_curve,
    compute_exit_reason_breakdown,
    compute_rolling_expectancy,
    compute_summary,
    compute_symbol_breakdown,
    derive_analytics_row,
)


def make_trade(
    *,
    agent_name: str = "test_agent",
    symbol: str = "AAPL",
    net_pnl: str = "100",
    gross_pnl: str = "110",
    exit_time: str = "2026-03-25T14:00:00Z",
    hold_minutes: float = 60.0,
    realized_outcome: str = "win",
    exit_reason: str = "profit_target",
    **kwargs: object,
) -> dict:
    return {
        "tracked_position_id": kwargs.get("id", 1),
        "agent_name": agent_name,
        "symbol": symbol,
        "net_pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "exit_time": exit_time,
        "hold_minutes": hold_minutes,
        "realized_outcome": realized_outcome,
        "exit_reason": exit_reason,
        "side": "buy",
        "entry_price": "100",
        "exit_price": "110",
        "entry_quantity": 10,
        "entry_fees": "5",
        "exit_fees": "5",
        "gross_return_pct": 0.1,
        "net_return_pct": 0.09,
        **kwargs,
    }


class TestComputeSummaryBasic:
    def test_compute_summary_basic(self) -> None:
        trades = [
            make_trade(net_pnl="100", gross_pnl="110", realized_outcome="win", exit_time="2026-03-25T10:00:00Z"),
            make_trade(net_pnl="50", gross_pnl="60", realized_outcome="win", exit_time="2026-03-25T11:00:00Z"),
            make_trade(net_pnl="-30", gross_pnl="-25", realized_outcome="loss", exit_time="2026-03-25T12:00:00Z"),
            make_trade(net_pnl="0", gross_pnl="0", realized_outcome="flat", exit_time="2026-03-25T13:00:00Z"),
        ]
        s = compute_summary(trades)
        assert s.trade_count == 4
        assert s.win_count == 2
        assert s.loss_count == 1
        assert s.flat_count == 1
        assert s.win_rate == 0.5
        # expectancy = 0.5 * 75 + 0.25 * (-30) = 37.5 - 7.5 = 30
        assert Decimal(s.expectancy) == Decimal("30")
        # profit_factor = 150 / 30 = 5.0
        assert s.profit_factor == 5.0

    def test_compute_summary_no_losses(self) -> None:
        trades = [
            make_trade(net_pnl="100", realized_outcome="win", exit_time="2026-03-25T10:00:00Z"),
            make_trade(net_pnl="50", realized_outcome="win", exit_time="2026-03-25T11:00:00Z"),
        ]
        s = compute_summary(trades)
        assert s.profit_factor is None

    def test_compute_summary_no_wins(self) -> None:
        trades = [
            make_trade(net_pnl="-100", realized_outcome="loss", exit_time="2026-03-25T10:00:00Z"),
            make_trade(net_pnl="-50", realized_outcome="loss", exit_time="2026-03-25T11:00:00Z"),
        ]
        s = compute_summary(trades)
        assert s.profit_factor == 0.0

    def test_compute_summary_empty(self) -> None:
        s = compute_summary([])
        assert s.agent_name == ""
        assert s.trade_count == 0
        assert s.win_rate == 0.0
        assert s.expectancy == "0"
        assert s.profit_factor is None


class TestComputeSummaryDrawdown:
    def test_compute_summary_drawdown(self) -> None:
        # net_pnl sequence: +100, +50, -80, -40, +200
        # cumulative:        100,  150,  70,  30, 230
        # peak:              100,  150, 150, 150, 230
        # drawdown:            0,    0,  80, 120,   0
        # max drawdown = -120
        trades = [
            make_trade(net_pnl="100", realized_outcome="win", exit_time="2026-03-25T10:00:00Z"),
            make_trade(net_pnl="50", realized_outcome="win", exit_time="2026-03-25T11:00:00Z"),
            make_trade(net_pnl="-80", realized_outcome="loss", exit_time="2026-03-25T12:00:00Z"),
            make_trade(net_pnl="-40", realized_outcome="loss", exit_time="2026-03-25T13:00:00Z"),
            make_trade(net_pnl="200", realized_outcome="win", exit_time="2026-03-25T14:00:00Z"),
        ]
        s = compute_summary(trades)
        assert Decimal(s.max_drawdown) == Decimal("-120")


class TestComputeEquityCurve:
    def test_compute_equity_curve(self) -> None:
        trades = [
            make_trade(net_pnl="100", exit_time="2026-03-25T10:00:00Z"),
            make_trade(net_pnl="-30", exit_time="2026-03-25T11:00:00Z"),
            make_trade(net_pnl="50", exit_time="2026-03-25T12:00:00Z"),
        ]
        curve = compute_equity_curve(trades)
        assert len(curve) == 3
        assert curve[0].exit_time == "2026-03-25T10:00:00Z"
        assert Decimal(curve[0].cumulative_net_pnl) == Decimal("100")
        assert Decimal(curve[1].cumulative_net_pnl) == Decimal("70")
        assert Decimal(curve[2].cumulative_net_pnl) == Decimal("120")


class TestComputeRollingExpectancy:
    def test_compute_rolling_expectancy(self) -> None:
        trades = [
            make_trade(net_pnl="100", realized_outcome="win", exit_time="2026-03-25T10:00:00Z"),
            make_trade(net_pnl="-50", realized_outcome="loss", exit_time="2026-03-25T11:00:00Z"),
            make_trade(net_pnl="80", realized_outcome="win", exit_time="2026-03-25T12:00:00Z"),
        ]
        points = compute_rolling_expectancy(trades, window=2)
        assert len(points) == 2

        # Window [0:2] = win(100), loss(-50): wr=0.5, lr=0.5, avg_win=100, avg_loss=-50
        # expectancy = 0.5*100 + 0.5*(-50) = 25
        assert Decimal(points[0].rolling_expectancy) == Decimal("25")

        # Window [1:3] = loss(-50), win(80): wr=0.5, lr=0.5, avg_win=80, avg_loss=-50
        # expectancy = 0.5*80 + 0.5*(-50) = 15
        assert Decimal(points[1].rolling_expectancy) == Decimal("15")


class TestComputeSymbolBreakdown:
    def test_compute_symbol_breakdown(self) -> None:
        trades = [
            make_trade(symbol="AAPL", net_pnl="100", realized_outcome="win"),
            make_trade(symbol="AAPL", net_pnl="-30", realized_outcome="loss"),
            make_trade(symbol="TSLA", net_pnl="200", realized_outcome="win"),
        ]
        breakdown = compute_symbol_breakdown(trades)
        assert len(breakdown) == 2

        aapl = next(b for b in breakdown if b.symbol == "AAPL")
        assert aapl.trade_count == 2
        assert aapl.win_rate == 0.5
        assert Decimal(aapl.net_pnl) == Decimal("70")

        tsla = next(b for b in breakdown if b.symbol == "TSLA")
        assert tsla.trade_count == 1
        assert tsla.win_rate == 1.0
        assert Decimal(tsla.net_pnl) == Decimal("200")


# ---------------------------------------------------------------------------
# derive_analytics_row tests
# ---------------------------------------------------------------------------


def _make_position(**overrides: object) -> dict:
    base = {
        "id": 1,
        "agent_name": "test_agent",
        "opportunity_id": "opp-1",
        "symbol": "AAPL",
        "side": "buy",
        "entry_price": "100",
        "exit_price": "110",
        "entry_quantity": 10,
        "entry_fees": "5",
        "exit_fees": "5",
        "entry_time": "2026-03-25T10:00:00Z",
        "exit_time": "2026-03-25T14:00:00Z",
        "exit_reason": "profit_target",
        "broker_id": None,
        "account_id": None,
    }
    base.update(overrides)
    return base


class TestDeriveAnalyticsRow:
    def test_winning_long_trade(self) -> None:
        row = derive_analytics_row(_make_position())
        # gross = (110-100)*10 = 100, net = 100-5-5 = 90
        assert Decimal(row["gross_pnl"]) == Decimal("100")
        assert Decimal(row["net_pnl"]) == Decimal("90")
        assert row["realized_outcome"] == "win"
        assert row["hold_minutes"] == 240.0

    def test_losing_short_trade(self) -> None:
        pos = _make_position(side="sell", entry_price="200", exit_price="210")
        row = derive_analytics_row(pos)
        # gross = (200-210)*10 = -100, net = -100-5-5 = -110
        assert Decimal(row["gross_pnl"]) == Decimal("-100")
        assert Decimal(row["net_pnl"]) == Decimal("-110")
        assert row["realized_outcome"] == "loss"

    def test_side_normalization(self) -> None:
        pos = _make_position(side="long")
        row = derive_analytics_row(pos)
        # "long" normalized to "buy", same math as winning long
        assert Decimal(row["gross_pnl"]) == Decimal("100")
        assert row["side"] == "long"  # original side preserved

    def test_short_normalization(self) -> None:
        pos = _make_position(side="short", entry_price="200", exit_price="190")
        row = derive_analytics_row(pos)
        # "short" normalized to "sell": gross = (200-190)*10 = 100
        assert Decimal(row["gross_pnl"]) == Decimal("100")
        assert row["realized_outcome"] == "win"

    def test_missing_opportunity(self) -> None:
        row = derive_analytics_row(_make_position(), opportunity=None)
        assert row["confidence"] is None
        assert row["signal"] is None

    def test_with_opportunity(self) -> None:
        opp = {"confidence": 0.85, "signal": "rsi_oversold"}
        row = derive_analytics_row(_make_position(), opportunity=opp)
        assert row["confidence"] == 0.85
        assert row["signal"] == "rsi_oversold"

    def test_execution_fills_averaging(self) -> None:
        fills = [
            {"slippage_bps": 5.0},
            {"slippage_bps": 15.0},
        ]
        row = derive_analytics_row(_make_position(), execution_fills=fills)
        assert row["execution_slippage_bps"] == 10.0

    def test_execution_fills_with_none(self) -> None:
        fills = [
            {"slippage_bps": 10.0},
            {"slippage_bps": None},
        ]
        row = derive_analytics_row(_make_position(), execution_fills=fills)
        assert row["execution_slippage_bps"] == 10.0

    def test_flat_trade(self) -> None:
        pos = _make_position(entry_price="100", exit_price="101", entry_fees="5", exit_fees="5")
        row = derive_analytics_row(pos)
        # gross = (101-100)*10 = 10, net = 10-5-5 = 0
        assert Decimal(row["net_pnl"]) == Decimal("0")
        assert row["realized_outcome"] == "flat"

    def test_enriches_from_signal_features_and_suggested_trade(self) -> None:
        opp = {
            "confidence": 0.85,
            "signal": "rsi_oversold",
            "data": {"strategy_version": "v2"},
            "suggested_trade": {"limit_price": "101.25"},
        }
        signal_features = {
            "confidence": 0.82,
            "feature_version": "1.0-backfill",
            "spread_bps": 12.5,
            "feature_payload": {"order_type": "limit"},
        }

        row = derive_analytics_row(
            _make_position(),
            opportunity=opp,
            signal_features=signal_features,
        )

        assert row["confidence_bucket"] == "0.80-0.90"
        assert row["strategy_version"] == "1.0-backfill"
        assert row["entry_spread_bps"] == 12.5
        assert row["order_type"] == "limit"
