from __future__ import annotations
import os
import sys
import asyncio
import logging
from datetime import date
from decimal import Decimal
from typing import List, Optional

# Add project root and trading to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, "trading"))

from fastmcp import FastMCP
import yfinance as yf
import pandas as pd

from trading.broker.models import Bar, Symbol, AssetType
from trading.backtesting.models import BacktestConfig
from trading.backtesting.taoshi_engine import TaoshiBacktestEngine

# Initialize FastMCP
mcp = FastMCP("Backtest")

logger = logging.getLogger("backtest_mcp")

@mcp.tool()
async def run_taoshi_backtest(
    symbols: List[str],
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    slippage_bps: float = 2.0,
) -> str:
    """
    Run a Taoshi consensus strategy backtest for a set of symbols and date range.
    
    Args:
        symbols: List of tickers (e.g. ["BTCUSD", "EURUSD"])
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        initial_capital: Starting cash balance
        slippage_bps: Slippage in basis points per trade
    """
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
        
        taoshi_root = os.path.join(PROJECT_ROOT, "taoshi-ptn")
        
        config = BacktestConfig(
            name=f"MCP_Backtest_{start_date}_{end_date}",
            agent_names=["bittensor_alpha"],
            symbols=symbols,
            start_date=sd,
            end_date=ed,
            timeframe="1h",
            initial_capital=Decimal(str(initial_capital)),
            slippage_bps=slippage_bps,
            metadata={
                "agent_parameters": {
                    "min_agreement": 0.6,
                    "min_return": 0.001
                }
            }
        )

        # Mapping for yfinance
        ticker_map = {
            "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
            "DOGEUSD": "DOGE-USD", "XRPUSD": "XRP-USD", "LTCUSD": "LTC-USD",
            "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
            "AUDUSD": "AUDUSD=X", "XAUUSD": "GC=F", "XAGUSD": "SI=F",
        }

        # Fetch data
        historical_data = {}
        for s in symbols:
            yf_ticker = ticker_map.get(s, f"{s}=X")
            df = yf.download(yf_ticker, start=sd, end=ed, interval="1h", progress=False)
            if df.empty:
                continue
                
            bars = []
            for ts, row in df.iterrows():
                try:
                    if isinstance(df.columns, pd.MultiIndex):
                        close_val = float(row['Close'][yf_ticker])
                    else:
                        close_val = float(row['Close'])
                except Exception:
                    close_val = float(row.iloc[3])

                bars.append(Bar(
                    symbol=Symbol(ticker=s),
                    timestamp=ts.to_pydatetime(),
                    close=Decimal(str(close_val))
                ))
            historical_data[s] = bars

        if not historical_data:
            return "Error: No historical data found for provided symbols."

        engine = TaoshiBacktestEngine(taoshi_root)
        result = await engine.run(config, historical_data)
        
        summary = (
            f"Backtest Complete: {result.status}\n"
            f"Total Return: {result.total_return_pct:.2f}%\n"
            f"Sharpe Ratio: {result.sharpe_ratio:.2f}\n"
            f"Max Drawdown: {result.max_drawdown_pct:.2f}%\n"
            f"Total Trades: {len(result.trades)}\n"
            f"Win Rate: {result.win_rate:.2f}%"
        )
        return summary

    except Exception as e:
        return f"Backtest failed: {str(e)}"

if __name__ == "__main__":
    mcp.run()
