import json
import pytest
import aiosqlite
from datetime import datetime, date
from decimal import Decimal

from data.backtest import BacktestResult
from learning.optimizer import generate_grid, GridSearchOptimizer
from storage.db import init_db


class TestGenerateGrid:
    def test_generate_grid_single_param(self):
        """Test generate_grid with one param: min=20, max=40, step=10 -> 3 combos."""
        spec = {"rsi_threshold": {"min": 20, "max": 40, "step": 10}}
        result = generate_grid(spec)
        
        assert len(result) == 3
        assert {"rsi_threshold": 20} in result
        assert {"rsi_threshold": 30} in result
        assert {"rsi_threshold": 40} in result
    
    def test_generate_grid_two_params(self):
        """Test generate_grid with two params -> 4 combos (2x2)."""
        spec = {
            "rsi_threshold": {"min": 20, "max": 30, "step": 10},
            "lookback": {"min": 7, "max": 14, "step": 7}
        }
        result = generate_grid(spec)
        
        assert len(result) == 4
        assert {"rsi_threshold": 20, "lookback": 7} in result
        assert {"rsi_threshold": 20, "lookback": 14} in result
        assert {"rsi_threshold": 30, "lookback": 7} in result
        assert {"rsi_threshold": 30, "lookback": 14} in result
    
    def test_generate_grid_empty(self):
        """Test generate_grid with empty spec -> [{}]."""
        spec = {}
        result = generate_grid(spec)
        
        assert len(result) == 1
        assert result == [{}]


class TestGridSearchOptimizer:
    @pytest.fixture
    async def db(self):
        """Create in-memory SQLite database for testing."""
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await init_db(db)
        yield db
        await db.close()
    
    @pytest.mark.asyncio
    async def test_save_result(self, db):
        """Test saving a backtest result to the database."""
        optimizer = GridSearchOptimizer(db)
        
        result = BacktestResult(
            agent_name="test_agent",
            parameters={"rsi_threshold": 30, "lookback": 14},
            sharpe_ratio=1.5,
            profit_factor=2.0,
            total_pnl=Decimal("10000.50"),
            max_drawdown=0.15,
            win_rate=0.65,
            total_trades=100,
            run_date=datetime.now(),
            data_start=date(2024, 1, 1),
            data_end=date(2024, 12, 31)
        )
        
        await optimizer.save_result(result)
        
        # Verify it was inserted
        cursor = await db.execute(
            "SELECT * FROM backtest_results WHERE agent_name = ?",
            ("test_agent",)
        )
        row = await cursor.fetchone()
        assert row is not None
        
        # Check values
        assert row["agent_name"] == "test_agent"
        assert row["sharpe_ratio"] == 1.5
        assert row["profit_factor"] == 2.0
        assert row["total_pnl"] == "10000.50"
        assert row["max_drawdown"] == 0.15
        assert row["win_rate"] == 0.65
        assert row["total_trades"] == 100
        
        # Verify parameters are stored as JSON
        params = json.loads(row["parameters"])
        assert params == {"rsi_threshold": 30, "lookback": 14}
    
    @pytest.mark.asyncio
    async def test_get_top_results(self, db):
        """Test retrieving top results ordered by sharpe_ratio DESC, profit_factor DESC."""
        optimizer = GridSearchOptimizer(db)
        
        # Insert multiple results
        results = [
            BacktestResult(
                agent_name="test_agent",
                parameters={"rsi_threshold": 20},
                sharpe_ratio=0.8,
                profit_factor=1.5,
                total_pnl=Decimal("5000"),
                max_drawdown=0.20,
                win_rate=0.55,
                total_trades=50,
                run_date=datetime.now(),
                data_start=date(2024, 1, 1),
                data_end=date(2024, 12, 31)
            ),
            BacktestResult(
                agent_name="test_agent",
                parameters={"rsi_threshold": 30},
                sharpe_ratio=2.0,
                profit_factor=2.5,
                total_pnl=Decimal("15000"),
                max_drawdown=0.10,
                win_rate=0.70,
                total_trades=100,
                run_date=datetime.now(),
                data_start=date(2024, 1, 1),
                data_end=date(2024, 12, 31)
            ),
            BacktestResult(
                agent_name="test_agent",
                parameters={"rsi_threshold": 40},
                sharpe_ratio=1.2,
                profit_factor=1.8,
                total_pnl=Decimal("8000"),
                max_drawdown=0.15,
                win_rate=0.62,
                total_trades=80,
                run_date=datetime.now(),
                data_start=date(2024, 1, 1),
                data_end=date(2024, 12, 31)
            ),
        ]
        
        for r in results:
            await optimizer.save_result(r)
        
        # Get top 3
        top_results = await optimizer.get_top_results("test_agent", limit=3)
        
        assert len(top_results) == 3
        # First should be sharpe=2.0 (highest)
        assert top_results[0]["sharpe_ratio"] == 2.0
        assert top_results[0]["profit_factor"] == 2.5
        # Second should be sharpe=1.2
        assert top_results[1]["sharpe_ratio"] == 1.2
        # Third should be sharpe=0.8
        assert top_results[2]["sharpe_ratio"] == 0.8
    
    @pytest.mark.asyncio
    async def test_get_top_results_with_limit(self, db):
        """Test limit parameter in get_top_results."""
        optimizer = GridSearchOptimizer(db)
        
        # Insert 5 results
        for i in range(5):
            result = BacktestResult(
                agent_name="test_agent",
                parameters={"param": i},
                sharpe_ratio=float(5 - i),  # Descending sharpe ratios
                profit_factor=1.0 + i,
                total_pnl=Decimal("1000"),
                max_drawdown=0.10,
                win_rate=0.60,
                total_trades=10,
                run_date=datetime.now(),
                data_start=date(2024, 1, 1),
                data_end=date(2024, 12, 31)
            )
            await optimizer.save_result(result)
        
        # Get top 2
        top_results = await optimizer.get_top_results("test_agent", limit=2)
        
        assert len(top_results) == 2
        assert top_results[0]["sharpe_ratio"] == 5.0
        assert top_results[1]["sharpe_ratio"] == 4.0
