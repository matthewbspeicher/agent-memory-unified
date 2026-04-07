# Quantitative Models & Formulas

## Performance Metrics

### 1. Sharpe Ratio
Measures the performance of an investment compared to a risk-free asset, after adjusting for its risk.
$$Sharpe = \frac{R_p - R_f}{\sigma_p}$$
- $R_p$: Expected portfolio return
- $R_f$: Risk-free rate
- $\sigma_p$: Standard deviation of portfolio excess return

### 2. Sortino Ratio
A variation of the Sharpe ratio that only differentiates harmful volatility from total overall volatility by using the asset's standard deviation of negative portfolio returns—downside deviation—instead of the total standard deviation of portfolio returns.
$$Sortino = \frac{R_p - R_f}{\sigma_d}$$
- $\sigma_d$: Downside deviation

## Risk Models

### 3. Value at Risk (VaR)
Estimate of the maximum loss over a certain period with a given confidence level.
- **Parametric VaR**: $VaR = PortfolioValue \times (Z \times \sigma - \mu)$
- **Monte Carlo VaR**: Percentile of simulated returns.

### 4. Maximum Drawdown (MDD)
The maximum observed loss from a peak to a trough of a portfolio, before a new peak is attained.
$$MDD = \frac{TroughValue - PeakValue}{PeakValue}$$

## Market Regimes

### 5. Volatility Index (VIX-style)
Calculated using the standard deviation of logarithmic returns over a sliding window (typically 20-30 days).

### 6. Average True Range (ATR)
Measures market volatility by decomposing the entire range of an asset price for that period.
$$TR = \max[(High - Low), |High - Close_{prev}|, |Low - Close_{prev}|]$$
$$ATR = \frac{1}{n} \sum_{i=1}^{n} TR_i$$
