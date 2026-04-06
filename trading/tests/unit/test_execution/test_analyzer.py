"""Tests for ExecutionAnalyzer — TDD phase."""

from decimal import Decimal

from execution.analyzer import ExecutionAnalyzer
from execution.tracker import ExecutionFill


def _fill(agent: str, slippage_bps: float, symbol: str = "AAPL") -> ExecutionFill:
    """Helper to create a fill with a target slippage_bps."""
    # slippage_bps = (actual - expected) / expected * 10000 for BUY
    expected = Decimal("100.00")
    diff = Decimal(str(slippage_bps)) * expected / Decimal("10000")
    actual = expected + diff
    return ExecutionFill(
        opportunity_id="opp-1",
        agent_name=agent,
        broker_id="ibkr",
        symbol=symbol,
        side="BUY",
        expected_price=expected,
        actual_price=actual,
        quantity=Decimal("10"),
    )


class TestExecutionAnalyzer:
    def test_no_edge_erosion_low_slippage(self):
        analyzer = ExecutionAnalyzer(erosion_threshold_bps=50.0)
        fills = [_fill("alpha", 5.0) for _ in range(5)]
        assert analyzer.is_eroding_edge("alpha", fills) is False

    def test_edge_erosion_detected_high_slippage(self):
        analyzer = ExecutionAnalyzer(erosion_threshold_bps=50.0)
        fills = [_fill("alpha", 80.0) for _ in range(5)]
        assert analyzer.is_eroding_edge("alpha", fills) is True

    def test_summary_returns_correct_stats(self):
        analyzer = ExecutionAnalyzer(erosion_threshold_bps=50.0)
        fills = [
            _fill("alpha", 10.0),
            _fill("alpha", 30.0),
            _fill("alpha", 20.0),
        ]
        summary = analyzer.summary("alpha", fills)
        assert summary["agent_name"] == "alpha"
        assert summary["fill_count"] == 3
        assert abs(summary["avg_slippage_bps"] - 20.0) < 1
        assert summary["edge_eroding"] is False

    def test_empty_fills_no_crash(self):
        analyzer = ExecutionAnalyzer(erosion_threshold_bps=50.0)
        assert analyzer.is_eroding_edge("alpha", []) is False
        summary = analyzer.summary("alpha", [])
        assert summary["fill_count"] == 0

    def test_worst_slippage_tracked(self):
        analyzer = ExecutionAnalyzer(erosion_threshold_bps=50.0)
        fills = [
            _fill("alpha", 5.0),
            _fill("alpha", 100.0),
            _fill("alpha", 10.0),
        ]
        summary = analyzer.summary("alpha", fills)
        assert summary["max_slippage_bps"] >= 90.0  # ~100 bps fill
