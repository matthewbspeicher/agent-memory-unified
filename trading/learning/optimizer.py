from __future__ import annotations

import json
from itertools import product

import aiosqlite

from data.backtest import BacktestResult


def generate_grid(optimization_spec: dict) -> list[dict]:
    """
    Generate all parameter combinations from an optimization spec.

    Takes a dict like:
    {
        "rsi_threshold": {"min": 20, "max": 40, "step": 10},
        "lookback": {"min": 7, "max": 14, "step": 7}
    }

    Returns a list of dicts with all cartesian product combinations.
    If spec is empty, returns [{}].

    Uses itertools.product and handles float tolerance when stepping.
    """
    if not optimization_spec:
        return [{}]

    param_names = list(optimization_spec.keys())
    param_values = []

    for name in param_names:
        spec = optimization_spec[name]
        min_val = spec["min"]
        max_val = spec["max"]
        step = spec["step"]

        values = []
        v = min_val
        # Use tolerance to handle floating point precision
        while v <= max_val + step * 0.001:
            values.append(v)
            v += step

        param_values.append(values)

    # Generate cartesian product
    combinations = []
    for combo in product(*param_values):
        combo_dict = dict(zip(param_names, combo))
        combinations.append(combo_dict)

    return combinations


class GridSearchOptimizer:
    """
    Stores and retrieves backtest results from a database.
    Used to track parameter optimization results across multiple backtests.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        """Initialize with aiosqlite connection."""
        self.db = db

    async def save_result(self, result: BacktestResult) -> None:
        """
        Insert a BacktestResult into the backtest_results table.

        Parameters are stored as JSON. Decimal fields are converted to strings.
        """
        # Convert parameters to JSON
        parameters_json = json.dumps(result.parameters)

        # Convert Decimal to string for storage
        total_pnl_str = str(result.total_pnl)

        await self.db.execute(
            """
            INSERT INTO backtest_results
            (agent_name, parameters, sharpe_ratio, profit_factor, total_pnl,
             max_drawdown, win_rate, total_trades, run_date, data_start, data_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.agent_name,
                parameters_json,
                result.sharpe_ratio,
                result.profit_factor,
                total_pnl_str,
                result.max_drawdown,
                result.win_rate,
                result.total_trades,
                result.run_date.isoformat(),
                result.data_start.isoformat(),
                result.data_end.isoformat(),
            ),
        )
        await self.db.commit()

    async def get_top_results(
        self, agent_name: str, limit: int = 3
    ) -> list[dict]:
        """
        Retrieve top backtest results for an agent.

        Results are ordered by sharpe_ratio DESC, then profit_factor DESC.
        Returns up to `limit` results as a list of dicts.
        """
        cursor = await self.db.execute(
            """
            SELECT
                id, agent_name, parameters, sharpe_ratio, profit_factor,
                total_pnl, max_drawdown, win_rate, total_trades,
                run_date, data_start, data_end
            FROM backtest_results
            WHERE agent_name = ?
            ORDER BY sharpe_ratio DESC, profit_factor DESC
            LIMIT ?
            """,
            (agent_name, limit),
        )
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "agent_name": row[1],
                    "parameters": json.loads(row[2]),
                    "sharpe_ratio": row[3],
                    "profit_factor": row[4],
                    "total_pnl": row[5],
                    "max_drawdown": row[6],
                    "win_rate": row[7],
                    "total_trades": row[8],
                    "run_date": row[9],
                    "data_start": row[10],
                    "data_end": row[11],
                }
            )

        return results
