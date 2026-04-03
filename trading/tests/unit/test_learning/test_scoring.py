from datetime import datetime, timezone, date
from decimal import Decimal

from data.backtest import score_backtest_run


def make_snapshot(time: datetime, equity: Decimal, executed: int = 0) -> dict:
    return {
        "time": time,
        "equity": equity,
        "cash": equity,
        "opportunities": 0,
        "executed": executed,
    }


def test_score_backtest_run():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshots = [
        make_snapshot(
            datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            Decimal(str(100_000 + i * 100)),
            executed=1,
        )
        for i in range(30)
    ]
    initial_equity = Decimal("100000")
    final_equity = Decimal("102900")

    result = score_backtest_run(
        agent_name="test-agent",
        parameters={"threshold": 0.5},
        snapshots=snapshots,
        initial_equity=initial_equity,
        final_equity=final_equity,
    )

    assert result.total_pnl == Decimal("2900")
    assert result.sharpe_ratio > 0
    assert result.max_drawdown == 0.0
    assert result.data_start == date(2026, 1, 1)
    assert result.data_end == date(2026, 1, 30)
    assert result.total_trades == 30
    assert result.agent_name == "test-agent"


def test_score_backtest_run_with_drawdown():
    snapshots = [
        make_snapshot(datetime(2026, 1, 1, tzinfo=timezone.utc), Decimal("100000")),
        make_snapshot(datetime(2026, 1, 2, tzinfo=timezone.utc), Decimal("105000")),
        make_snapshot(datetime(2026, 1, 3, tzinfo=timezone.utc), Decimal("95000")),
        make_snapshot(datetime(2026, 1, 4, tzinfo=timezone.utc), Decimal("102000")),
    ]

    result = score_backtest_run(
        agent_name="drawdown-agent",
        parameters={},
        snapshots=snapshots,
        initial_equity=Decimal("100000"),
        final_equity=Decimal("102000"),
    )

    # peak = 105000, trough = 95000 → (105000 - 95000) / 105000 ≈ 0.09524
    assert abs(result.max_drawdown - (10000 / 105000)) < 1e-6
