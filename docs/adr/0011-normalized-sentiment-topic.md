# ADR-0011: Normalized Sentiment Topic on the SignalBus

**Status**: accepted

**Date**: 2026-05-22
**Deciders**: matth

---

## Context

The `IntelligenceLayer` already aggregates a normalized sentiment score from three providers — Crypto Fear & Greed Index, LunarCrush, Alpha Vantage AI sentiment — and exposes it as an `IntelReport(source="sentiment", score, confidence, details)`. Today the report has exactly one consumer: `enrich_confidence()`, which mixes it into the `intel_enriched_consensus` payload for `bittensor_consensus` signals. Every other agent that wants sentiment has to re-derive it from raw inputs.

Three concrete consumers will exist in the near term:

1. **`bittensor_alpha_ensemble`** (already configured in `agents.yaml`) declares `intel_weights.sentiment: 0.15` but only receives sentiment via the enriched-consensus channel — it cannot reach the raw score independently.
2. **Persona LLM agents** planned for `agents.paper.yaml` (Buffett, Graham, Lynch, Munger, Klarman, Marks) need sentiment as input context.
3. **Future strategies** that want to gate trade decisions on sentiment without subscribing to `bittensor_consensus`.

Without a shared topic each consumer either subscribes to `intel_enriched_consensus` (and inherits the consensus path's coupling), or re-implements its own sentiment derivation against the same providers, or goes without.

Note: this is distinct from the existing `sentiment_spike` signal type, which fires only on social-sentiment bursts (Twitter imbalance). `intel_sentiment` is the *aggregate normalized score* that `IntelligenceLayer` already computes every enrichment cycle but never publishes.

## Decision

Publish the `IntelligenceLayer`'s sentiment report as a typed SignalBus signal of type **`intel_sentiment`** whenever a fresh report is gathered, regardless of whether another provider vetoes the consensus enrichment.

### Payload contract

Defined in `trading/data/signal_types.py`:

```python
class IntelSentimentPayload(SignalPayload):
    symbol: str
    score: float          # -1.0 .. +1.0  (bearish to bullish)
    confidence: float     #  0.0 .. 1.0
    sources: dict         # provider-specific raw values (fear_greed_value, …)
```

Registered as `"intel_sentiment"` in the global `SignalTypeRegistry`. Signals expire after 15 minutes.

### Publishing site

`IntelligenceLayer._gather_intel()` iterates the gathered reports and calls a new `_publish_sentiment(report)` helper for any `source="sentiment"` non-veto report. This fires **before** the veto-short-circuit so sentiment is still visible to downstream consumers even when, e.g., the risk-audit provider vetoes the enrichment path.

The helper is best-effort: a publish failure logs a warning and does not break the enrichment loop.

### Consumption contract

A new `Agent.consume_sentiment(symbol, max_age_seconds=300)` helper on the `Agent` base reads the freshest matching signal from `self.signal_bus` and returns its payload, or `None` when:

- No SignalBus is attached (test contexts).
- No sentiment exists for this symbol.
- The freshest matching signal is older than `max_age_seconds`.

Strategies opt in by calling `consume_sentiment()` inside `scan()`. No subscription model — strategies poll the bus on their own cadence.

## Consequences

### Positive

- **Locality**: every change to sentiment aggregation, weighting, or decay lives in `intelligence/`. Consumers know only the payload contract.
- **Leverage**: persona agents, `bittensor_alpha_ensemble`, and future strategies all read from one normalized topic with three lines of code.
- **No new poll loop**: piggybacks on the existing enrichment cycle, so sentiment is published exactly when `bittensor_consensus` signals arrive for a symbol. Frequency = consensus frequency.
- **Backward-compatible**: `intel_enriched_consensus` is unchanged; the new topic is purely additive.

### Negative

- Sentiment is only published for symbols that *also* see `bittensor_consensus` signals (currently BTCUSD, ETHUSD). Equity-only personas (e.g. Buffett, Graham) will get no sentiment unless we later add a proactive sentiment poller for arbitrary assets. Acceptable as a v1 limitation; tracked as a follow-up.
- Best-effort publish: a malformed report silently drops instead of blocking the enrichment cycle. Logged at WARNING.

### Neutral

- Bus growth: one extra signal per enrichment cycle. With the 15-minute TTL and `MAX_SIGNALS=1000` cap in `SignalBus`, the impact is negligible.

## File Map

| File | Action | Description |
|------|--------|-------------|
| `trading/data/signal_types.py` | Modified | Added `IntelSentimentPayload`; registered `"intel_sentiment"` |
| `trading/intelligence/layer.py` | Modified | Added `_publish_sentiment()`; invoked from `_gather_intel()` |
| `trading/agents/base.py` | Modified | Added `Agent.consume_sentiment(symbol, max_age_seconds)` |
| `trading/tests/unit/test_intel_sentiment_topic.py` | New | 12 tests covering payload, publish hook, and consume helper |
| `trading/tests/unit/test_signal_types.py` | Modified | Updated `test_registry_has_all_types` count 10 → 11 |
| `CONTEXT.md` | New | Lazy creation; pins Sentiment, SignalBus topic, Persona vocabulary |

## Follow-ups (not in this ADR)

- **Proactive sentiment poller** for equity assets so persona agents covering AAPL/MSFT/etc. receive sentiment. Likely a small async task in `IntelligenceLayer.start()` reading a configured universe.
- **Headlines as a separate topic** to retire duplicated RSS/NewsAPI/GDELT fetching in `kalshi_news_arb` and `polymarket_news_arb`. Distinct from sentiment — those strategies use headlines for per-market probability estimation, not for sentiment scores.

## References

- `trading/data/signal_types.py` — payload contract
- `trading/intelligence/layer.py:_publish_sentiment` — publishing site
- `trading/intelligence/providers/sentiment.py` — upstream report producer
- `trading/agents/base.py:consume_sentiment` — consumer helper
- ADR-0007: Two-process Bittensor architecture (separates this from the validator's signal path)
