# ADR-002: Regime-Aware Ensemble Strategies

**Status**: accepted

**Date**: 2026-04-07
**Deciders**: Development Team

---

## Context

The existing EnsembleOptimizer used static weights based on historical Sharpe ratios. Market conditions change, and different strategies perform better in different regimes.

## Decision

Add regime-aware ensemble capabilities:
1. **RegimeDetector** class that classifies market state (bull, bear, sideways, high_volatility, low_volatility)
2. **REGIME_WEIGHT_ADJUSTMENTS** dict that applies multipliers to different strategy types based on regime
3. **Config options**: `regime_aware`, `regime_lookback_bars`, `regime_volatility_threshold`, `regime_trend_threshold`

## Consequences

### Positive
- Dynamically adjusts to market conditions
- Boosts trend-following in bull markets, mean-reversion in sideways
- Reduces exposure during high volatility

### Negative
- Additional complexity in weight calculation
- Requires historical price data for regime detection

### Neutral
- Disabled by default - enable via `regime_aware: true` in config
- Works with all ensemble methods (weighted_average, majority_vote, etc.)

---

## Alternatives Considered

| Alternative | Pros | Cons |
|-------------|------|------|
| Static weights | Simple, proven | Doesn't adapt to regime |
| Online ML | Self-tuning | Harder to debug, more complex |
| Manual regime switching | Full control | Requires human intervention |

---

## Notes

- See `trading/learning/ensemble_optimizer.py` for implementation
- Regime detection uses linear regression for trend + std dev of returns for volatility
- Threshold defaults: trend_threshold=0.05 (5%), volatility_threshold=1.5 (1.5 std devs)
