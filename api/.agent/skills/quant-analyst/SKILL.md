---
name: quant-analyst
description: Quantitative analysis, signal validation, and risk assessment for trading. Use when validating signals, performing Monte Carlo simulations, or detecting market regimes.
---

# Quant Analyst Skill

Expert guidance for quantitative financial analysis within the Agent Memory Commons ecosystem.

## Core Capabilities

1. **Signal Validation**: Statistical verification of trading signals against historical regimes and volatility.
2. **Risk Assessment**: Portfolio risk modeling, including Value at Risk (VaR) and Monte Carlo simulations.
3. **Regime Detection**: Classification of market states (Bull/Bear, High/Low Vol) to inform strategy selection.
4. **Performance Attribution**: Analysis of Sharpe, Sortino, and Drawdown metrics for strategies and miners.

## Workflows

### 1. Validating a New Signal
When a signal is received from the SignalBus or a miner:
- Retrieve historical price action for the relevant symbol from `DataBus`.
- Perform a Z-score analysis to check if the current price move is an outlier.
- Cross-reference with similar historical "Memories" via the Vector Memory Loop.
- Output a confidence score (0-1).

### 2. Monte Carlo Risk Audit
To assess the risk of a proposed position or portfolio:
- Use `scripts/risk_analysis.py` to simulate 10,000 price paths based on historical volatility.
- Calculate the 95% and 99% VaR.
- Determine if the expected drawdown exceeds the threshold defined in `risk.yaml`.

### 3. Market Regime Detection
Before emitting a signal:
- Fetch the last 30-100 bars of data.
- Calculate ATR (Average True Range) and ADX (Trend Strength).
- Classify the regime: `trending_bull`, `trending_bear`, `volatile_range`, `quiet_range`.
- Store the regime in the `pgvector` memory loop for future recall.

## Tools & Resources

- **Mathematical Models**: See [models.md](references/models.md) for formulas.
- **Risk Script**: `python3 scripts/risk_analysis.py`
- **Regime Script**: `python3 scripts/regime_detector.py`
