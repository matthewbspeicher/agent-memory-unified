"""Walk-forward backtesting engine for overfitting detection.

Splits historical data into rolling train/test windows:

    Window 1: [====TRAIN====][==TEST==]
    Window 2:    [====TRAIN====][==TEST==]
    Window 3:       [====TRAIN====][==TEST==]
    ...

For each window:
1. Evaluate strategy performance on the train period
2. Evaluate on the out-of-sample test period
3. Compare train vs test metrics to detect overfitting

Overfit detection: if train_sharpe > threshold * test_sharpe consistently,
the strategy is likely overfit to historical noise.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class WindowResult:
    """Result of one train/test window."""

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_sharpe: float
    test_sharpe: float
    test_return: float
    test_max_drawdown: float
    test_trades: int
    is_overfit: bool  # True if train_sharpe >> test_sharpe


@dataclass
class WalkForwardResult:
    """Aggregate result across all walk-forward windows."""

    windows: list[WindowResult] = field(default_factory=list)
    avg_test_sharpe: float = 0.0
    avg_test_return: float = 0.0
    avg_test_max_drawdown: float = 0.0
    total_test_trades: int = 0
    overfit_ratio: float = 0.0  # fraction of windows where is_overfit=True
    walk_forward_efficiency: float = 0.0  # avg(test_sharpe) / avg(train_sharpe)


class WalkForwardEngine:
    """Walk-forward backtesting to detect overfitting.

    Splits historical data into rolling train/test windows and compares
    in-sample (train) vs out-of-sample (test) performance. A strategy
    that performs well in-sample but poorly out-of-sample is likely overfit.

    Parameters
    ----------
    train_days : int
        Number of days in each training window.
    test_days : int
        Number of days in each test window.
    step_days : int
        How many days to advance between successive windows.
    min_trades_per_window : int
        Minimum trades required per window (for trade-count metrics).
    overfit_threshold : float
        If train_sharpe > overfit_threshold * test_sharpe (and test_sharpe > 0),
        the window is flagged as overfit.
    """

    def __init__(
        self,
        train_days: int = 60,
        test_days: int = 20,
        step_days: int = 20,
        min_trades_per_window: int = 5,
        overfit_threshold: float = 2.0,
    ) -> None:
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.min_trades_per_window = min_trades_per_window
        self.overfit_threshold = overfit_threshold

    def generate_windows(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime, datetime, datetime]]:
        """Generate (train_start, train_end, test_start, test_end) tuples.

        Starting at *start*, each window has *train_days* of training followed
        by *test_days* of testing. Windows advance by *step_days*. Only
        windows whose test_end <= end are included.
        """
        windows: list[tuple[datetime, datetime, datetime, datetime]] = []
        train_delta = timedelta(days=self.train_days)
        test_delta = timedelta(days=self.test_days)
        step_delta = timedelta(days=self.step_days)

        current_start = start
        while True:
            train_end = current_start + train_delta
            test_start = train_end
            test_end = test_start + test_delta

            if test_end > end:
                break

            windows.append((current_start, train_end, test_start, test_end))
            current_start += step_delta

        return windows

    def evaluate_window(
        self,
        returns_train: list[float],
        returns_test: list[float],
        train_start: datetime,
        train_end: datetime,
        test_start: datetime,
        test_end: datetime,
    ) -> WindowResult:
        """Evaluate one train/test window.

        Computes Sharpe ratio and max drawdown for both periods.
        Flags overfitting if train Sharpe greatly exceeds test Sharpe.
        """
        train_sharpe = self.sharpe_ratio(returns_train)
        test_sharpe = self.sharpe_ratio(returns_test)
        test_return = (
            float(np.prod(1 + np.array(returns_test)) - 1) if returns_test else 0.0
        )
        test_dd = self.max_drawdown(returns_test)
        test_trades = len(
            returns_test
        )  # proxy: each day with a return counts as a trade

        # Overfit detection: train performance vastly exceeds test performance
        if test_sharpe > 0 and train_sharpe > self.overfit_threshold * test_sharpe:
            is_overfit = True
        elif test_sharpe <= 0 and train_sharpe > 0:
            # If test Sharpe is non-positive but train is positive, flag as overfit
            is_overfit = True
        else:
            is_overfit = False

        return WindowResult(
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            train_sharpe=train_sharpe,
            test_sharpe=test_sharpe,
            test_return=test_return,
            test_max_drawdown=test_dd,
            test_trades=test_trades,
            is_overfit=is_overfit,
        )

    def run(
        self,
        daily_returns: list[float],
        timestamps: list[datetime],
    ) -> WalkForwardResult:
        """Run full walk-forward analysis on a returns series.

        Args:
            daily_returns: Daily strategy returns (e.g. 0.01 = +1%).
            timestamps: Corresponding timestamps (same length as daily_returns).

        Returns:
            WalkForwardResult with all windows and aggregate metrics.
        """
        if not daily_returns or not timestamps:
            return WalkForwardResult()

        if len(daily_returns) != len(timestamps):
            raise ValueError(
                f"daily_returns ({len(daily_returns)}) and timestamps "
                f"({len(timestamps)}) must have the same length"
            )

        start = timestamps[0]
        end = timestamps[-1] + timedelta(days=1)  # inclusive of last day

        windows_spec = self.generate_windows(start, end)
        if not windows_spec:
            return WalkForwardResult()

        window_results: list[WindowResult] = []

        for train_start, train_end, test_start, test_end in windows_spec:
            # Gather returns that fall within each period
            returns_train = []
            returns_test = []

            for i, ts in enumerate(timestamps):
                if train_start <= ts < train_end:
                    returns_train.append(daily_returns[i])
                elif test_start <= ts < test_end:
                    returns_test.append(daily_returns[i])

            # Skip windows with insufficient data
            if len(returns_train) < 2 or len(returns_test) < 1:
                continue

            wr = self.evaluate_window(
                returns_train=returns_train,
                returns_test=returns_test,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
            window_results.append(wr)

        if not window_results:
            return WalkForwardResult()

        # Aggregate metrics
        avg_test_sharpe = float(np.mean([w.test_sharpe for w in window_results]))
        avg_train_sharpe = float(np.mean([w.train_sharpe for w in window_results]))
        avg_test_return = float(np.mean([w.test_return for w in window_results]))
        avg_test_dd = float(np.mean([w.test_max_drawdown for w in window_results]))
        total_trades = sum(w.test_trades for w in window_results)
        overfit_count = sum(1 for w in window_results if w.is_overfit)
        overfit_ratio = overfit_count / len(window_results)

        # Walk-forward efficiency: ratio of out-of-sample to in-sample Sharpe
        if avg_train_sharpe != 0:
            wf_efficiency = avg_test_sharpe / avg_train_sharpe
        else:
            wf_efficiency = 0.0

        logger.info(
            "Walk-forward complete: %d windows, avg_test_sharpe=%.3f, "
            "overfit_ratio=%.2f, efficiency=%.3f",
            len(window_results),
            avg_test_sharpe,
            overfit_ratio,
            wf_efficiency,
        )

        return WalkForwardResult(
            windows=window_results,
            avg_test_sharpe=avg_test_sharpe,
            avg_test_return=avg_test_return,
            avg_test_max_drawdown=avg_test_dd,
            total_test_trades=total_trades,
            overfit_ratio=overfit_ratio,
            walk_forward_efficiency=wf_efficiency,
        )

    @staticmethod
    def sharpe_ratio(returns: list[float], annualize: float = 365.0) -> float:
        """Annualized Sharpe ratio (assuming 0 risk-free rate for crypto).

        Parameters
        ----------
        returns : list[float]
            Period returns (e.g. daily).
        annualize : float
            Annualization factor (365 for daily crypto, 252 for equities).

        Returns
        -------
        float
            Annualized Sharpe ratio, or 0.0 if insufficient data or zero std.
        """
        if len(returns) < 2:
            return 0.0
        r = np.array(returns)
        std = r.std(ddof=1)
        if std == 0:
            return 0.0
        return float(r.mean() / std * np.sqrt(annualize))

    @staticmethod
    def max_drawdown(returns: list[float]) -> float:
        """Maximum drawdown from cumulative returns.

        Parameters
        ----------
        returns : list[float]
            Period returns.

        Returns
        -------
        float
            Maximum drawdown as a negative fraction (e.g. -0.30 = 30% drawdown),
            or 0.0 if no drawdown / empty input.
        """
        if not returns:
            return 0.0
        cum = np.cumprod(1 + np.array(returns))
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        return float(dd.min()) if len(dd) > 0 else 0.0

    def validate_parameters(
        self,
        base_returns: list[float],
        optimized_returns: list[float],
        timestamps: list[datetime],
    ) -> dict:
        """Validate optimized parameters using walk-forward analysis.

        Compares base strategy performance vs optimized parameters to ensure
        improvements are robust across time periods, not just overfit.

        Args:
            base_returns: Daily returns using original parameters.
            optimized_returns: Daily returns using optimized parameters.
            timestamps: Corresponding timestamps.

        Returns:
            Dict with comparison metrics and validation status.
        """
        base_result = self.run(base_returns, timestamps)
        optimized_result = self.run(optimized_returns, timestamps)

        # Walk-forward efficiency comparison
        base_efficiency = base_result.walk_forward_efficiency
        opt_efficiency = optimized_result.walk_forward_efficiency

        # Improvement metrics
        sharpe_improvement = (
            optimized_result.avg_test_sharpe - base_result.avg_test_sharpe
        )
        efficiency_improvement = opt_efficiency - base_efficiency

        # Validation: optimized should have better OOS performance AND reasonable efficiency
        is_valid = (
            optimized_result.avg_test_sharpe > base_result.avg_test_sharpe
            and opt_efficiency > 0.5  # At least 50% of in-sample performance transfers
            and optimized_result.overfit_ratio < 0.5  # Less than 50% windows overfit
        )

        return {
            "is_valid": is_valid,
            "base_metrics": {
                "avg_test_sharpe": base_result.avg_test_sharpe,
                "avg_test_return": base_result.avg_test_return,
                "walk_forward_efficiency": base_efficiency,
                "overfit_ratio": base_result.overfit_ratio,
            },
            "optimized_metrics": {
                "avg_test_sharpe": optimized_result.avg_test_sharpe,
                "avg_test_return": optimized_result.avg_test_return,
                "walk_forward_efficiency": opt_efficiency,
                "overfit_ratio": optimized_result.overfit_ratio,
            },
            "improvement": {
                "sharpe_delta": sharpe_improvement,
                "efficiency_delta": efficiency_improvement,
                "relative_sharpe_pct": (
                    (sharpe_improvement / abs(base_result.avg_test_sharpe) * 100)
                    if base_result.avg_test_sharpe != 0
                    else 0.0
                ),
            },
            "windows_analyzed": len(optimized_result.windows),
        }

    def run_multi_split(
        self,
        returns: list[float],
        timestamps: list[datetime],
        splits: list[tuple[int, int]] | None = None,
    ) -> dict[str, WalkForwardResult]:
        """Run walk-forward analysis with multiple train/test split configurations.

        Useful for sensitivity analysis - see how strategy performs under
        different window sizes.

        Args:
            returns: Daily returns.
            timestamps: Corresponding timestamps.
            splits: List of (train_days, test_days) tuples. Defaults to
                   [(30,7), (60,20), (90,30)].

        Returns:
            Dict mapping split config to WalkForwardResult.
        """
        if splits is None:
            splits = [(30, 7), (60, 20), (90, 30)]

        results = {}
        for train_days, test_days in splits:
            # Create temporary engine with different config
            temp_engine = WalkForwardEngine(
                train_days=train_days,
                test_days=test_days,
                step_days=test_days,
                min_trades_per_window=self.min_trades_per_window,
                overfit_threshold=self.overfit_threshold,
            )
            result = temp_engine.run(returns, timestamps)
            key = f"train{train_days}_test{test_days}"
            results[key] = result

            logger.info(
                "Multi-split %s: %d windows, avg_test_sharpe=%.3f, overfit=%.2f",
                key,
                len(result.windows),
                result.avg_test_sharpe,
                result.overfit_ratio,
            )

        return results
