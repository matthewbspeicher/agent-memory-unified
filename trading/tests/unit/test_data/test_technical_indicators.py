import pytest
import pandas as pd
import numpy as np
from data.indicators import add_technical_indicators

def test_add_technical_indicators():
    df = pd.DataFrame({
        "open": np.random.random(100),
        "high": np.random.random(100),
        "low": np.random.random(100),
        "close": np.random.random(100),
        "volume": np.random.random(100)
    })
    
    df_with_ta = add_technical_indicators(df)
    assert "RSI_14" in df_with_ta.columns
    assert "MACD_12_26_9" in df_with_ta.columns
