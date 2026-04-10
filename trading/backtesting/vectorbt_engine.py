from __future__ import annotations
import vectorbt as vbt
import pandas as pd

def run_vbt_backtest(prices: pd.Series, signals: pd.Series) -> dict:
    """Run a vectorized backtest using vectorbt."""
    # Convert signals to entries/exits
    # signals: 1 = Buy, -1 = Sell, 0 = Hold
    entries = signals == 1
    exits = signals == -1
    
    # Run portfolio simulation
    pf = vbt.Portfolio.from_signals(
        prices, 
        entries, 
        exits, 
        init_cash=10000,
        fees=0.001, # 10bps fee
        slippage=0.001, # 10bps slippage
        freq='1D' # Specify daily frequency for Sharpe calculation
    )
    
    return {
        "total_return": float(pf.total_return()),
        "sharpe_ratio": float(pf.sharpe_ratio()),
        "max_drawdown": float(pf.max_drawdown()),
        "win_rate": float(pf.trades.win_rate()),
        "trade_count": int(pf.trades.count())
    }
