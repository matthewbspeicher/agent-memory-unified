import pytest
import numpy as np
import pandas as pd
from backtesting.vectorbt_engine import run_vbt_backtest

def test_vectorbt_execution():
    # Mock some data
    prices = pd.Series(np.random.random(100) * 100)
    # Random signals: 1=buy, -1=sell, 0=none
    signals = pd.Series(np.random.choice([0, 1, -1], 100))
    
    result = run_vbt_backtest(prices, signals)
    
    assert 'total_return' in result
    assert 'sharpe_ratio' in result
    assert isinstance(result['total_return'], float)
