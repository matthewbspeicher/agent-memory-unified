# Market Intelligence Layer — Design Spec

**Date:** 2026-04-07
**Status:** Approved
**Author:** mspeicher + Claude

## Overview

A Market Intelligence Layer that enriches Bittensor miner consensus signals with on-chain analytics, market sentiment, and anomaly detection. The layer adjusts confidence scores on existing signals and provides a hard veto gate for extreme conditions.

This is **signal enrichment**, not a new trading strategy. Miners remain the primary signal source; intelligence providers nudge confidence up/down and can block trades in extreme scenarios.

## Architecture

```
MinerConsensusAggregator
  |  bittensor_consensus signal (via SignalBus)
  v
IntelligenceLayer (subscribes to consensus signals)
  |-- OnChainProvider   -> IntelReport (whale flows, exchange balances)
  |-- SentimentProvider -> IntelReport (fear/greed, social momentum)
  |-- AnomalyProvider   -> IntelReport (volume spikes, price divergence)
  v
Publishes: "intel_enriched_consensus" signal
  v
BittensorSignalAgent.scan()
  |-- reads enriched confidence (gates 1-8)
  |-- gate 9: checks veto flag from IntelReport
  v
Opportunity (with intel_summary in data{})
```

## Data Models

### IntelReport (common currency for all providers)

```python
@dataclass
class IntelReport:
    source: str          # "on_chain", "sentiment", "anomaly"
    symbol: str          # "BTCUSD"
    timestamp: datetime
    score: float         # -1.0 to +1.0 (bearish to bullish)
    confidence: float    # 0.0 to 1.0 (how sure is this source)
    veto: bool           # True = hard block this trade
    veto_reason: str | None
    details: dict        # source-specific data
```

### IntelEnrichment (output of enrichment calculation)

```python
@dataclass
class IntelEnrichment:
    vetoed: bool
    veto_reason: str | None = None
    base_confidence: float = 0.0
    adjustment: float = 0.0
    final_confidence: float = 0.0
    contributions: list[dict] = field(default_factory=list)
```

### IntelRecord (stored for backtesting)

```python
@dataclass
class IntelRecord:
    symbol: str
    timestamp: datetime
    provider: str
    report: IntelReport
    latency_ms: int
```

## Execution Model

**Async parallel with 2s timeout, early exit on veto.**

```python
async def gather_intel(self, symbol: str) -> list[IntelReport]:
    tasks = [
        self._call_with_circuit_breaker("on_chain", self.on_chain.analyze, symbol),
        self._call_with_circuit_breaker("sentiment", self.sentiment.analyze, symbol),
        self._call_with_circuit_breaker("anomaly", self.anomaly.analyze, symbol),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    reports = []
    for result in results:
        if isinstance(result, IntelReport):
            if result.veto:
                return [result]  # early exit on veto
            reports.append(result)
        elif isinstance(result, Exception):
            logger.warning("Intel provider failed: %s", result)
    return reports
```

- Timeout: 2s total via `asyncio.wait_for`
- If any provider vetos: return immediately (don't wait for others)
- If timeout: log warning, proceed with available reports
- If all fail: pass through unchanged (no enrichment, no blocking)

## Failure Modes

| Scenario | Behavior | Rationale |
|----------|----------|-----------|
| Provider errors | Log, continue with 2/3 | Don't block trading for intel |
| Provider returns None | Treat as score=0, confidence=0 | Neutral contribution |
| Provider stale data (>5min) | Reduce confidence by 50% | Trust but verify |
| All providers fail | Log, pass through unchanged | Don't block trading |
| Timeout | Log warning, proceed with available | Don't hang |

## Circuit Breaker

Each provider wrapped in a circuit breaker:

```python
class ProviderCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 60):
        self.failures: int = 0
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state: str = "closed"  # closed=ok, open=blocked, half_open=testing
        self.last_failure_time: datetime | None = None
```

- **Closed**: normal operation
- **Open** (3+ consecutive failures): skip provider for 60s, return None
- **Half-open** (after 60s): try one request; success resets to closed, failure reopens

## Confidence Enrichment

```python
def enrich_confidence(
    base_confidence: float,
    direction_score: float,
    reports: list[IntelReport],
    weights: dict[str, float],
) -> tuple[float, IntelEnrichment]:
    base_confidence = clamp(base_confidence, 0.0, 1.0)
    total_adjustment = 0.0
    contributions = []

    for report in reports:
        if report.veto:
            return 0.0, IntelEnrichment(vetoed=True, veto_reason=report.veto_reason)

        # Alignment: does report agree with miner direction?
        alignment = report.score * sign(direction_score)  # -1 to +1

        # v1: only boost on positive alignment (don't dampen from noisy intel)
        if alignment > 0:
            adjustment = alignment * report.confidence * weights.get(report.source, 0.0)
            total_adjustment += adjustment
            contributions.append({
                "source": report.source,
                "adjustment": adjustment,
                "alignment": alignment,
            })

    # Cap adjustment at 30% of base to prevent intel dominance
    max_adjustment = base_confidence * 0.30
    total_adjustment = clamp(total_adjustment, -max_adjustment, max_adjustment)
    enriched = clamp(base_confidence + total_adjustment, 0.0, 1.0)

    return enriched, IntelEnrichment(
        vetoed=False,
        base_confidence=base_confidence,
        adjustment=total_adjustment,
        final_confidence=enriched,
        contributions=contributions,
    )
```

**Default weights:** `{"on_chain": 0.15, "sentiment": 0.10, "anomaly": 0.05}`

**Design choice (v1):** Only positive alignment boosts confidence. Conflicting intel is ignored (not used to dampen). This is intentional — miners are the primary signal, intel is supplementary. Dampening from noisy sentiment data could degrade good signals. Revisit once we have accuracy data on providers.

## Veto Threshold

Default: **any** (1 veto from any provider blocks the trade).

Configurable:

```python
@dataclass
class IntelligenceConfig:
    timeout_ms: int = 2000
    min_providers: int = 1
    veto_threshold: int = 1       # 1=any, 2=majority
    weights: dict[str, float] = field(default_factory=lambda: {
        "on_chain": 0.15,
        "sentiment": 0.10,
        "anomaly": 0.05,
    })
    max_adjustment_pct: float = 0.30
    stale_data_threshold_seconds: int = 300
    circuit_breaker_failures: int = 3
    circuit_breaker_reset_seconds: int = 60
```

All config via `STA_INTEL_*` env vars following existing `STA_` prefix convention.

## Provider Designs

### 1. OnChainProvider

**Reads:** Exchange net flows, whale wallet movements, active address trends.

| Signal | Score Contribution |
|--------|-------------------|
| Net exchange outflow (accumulation) | +0.3 to +0.5 |
| Whale wallets accumulating | +0.2 to +0.4 |
| Active addresses rising | +0.1 to +0.2 |
| Net exchange inflow (distribution) | -0.3 to -0.5 |
| Whale wallets distributing | -0.2 to -0.4 |

**Veto condition:** Exchange inflow exceeds 2x 30-day average (dump signal).

**Data sources:** CoinGlass API, Glassnode (if key available), blockchain RPC for whale tracking. Falls back gracefully — if no API key configured, returns `None` (neutral).

**Env vars:** `STA_INTEL_COINGLASS_API_KEY`, `STA_INTEL_GLASSNODE_API_KEY` (optional)

### 2. SentimentProvider

**Reads:** Crypto Fear & Greed Index, social media momentum, news sentiment.

| Signal | Score Contribution |
|--------|-------------------|
| Fear & Greed > 75 (extreme greed) | -0.2 (contrarian) |
| Fear & Greed < 25 (extreme fear) | +0.2 (contrarian) |
| Fear & Greed 25-75 | Scaled linearly |
| Social volume spike + positive | +0.1 to +0.3 |
| Social volume spike + negative | -0.1 to -0.3 |

**Veto condition:** None. Sentiment is too noisy for hard stops.

**Data sources:** Alternative.me Fear & Greed API (free, no key needed), LunarCrush or Santiment if keys available.

**Env vars:** `STA_INTEL_LUNARCRUSH_API_KEY`, `STA_INTEL_SANTIMENT_API_KEY` (optional)

### 3. AnomalyProvider

**Reads:** Volume deviation from 20-period mean, price-volume divergence, spread abnormalities.

| Signal | Score Contribution |
|--------|-------------------|
| Volume 3x normal + price aligned | +0.2 (confirms direction) |
| Volume 3x normal + price diverges | -0.3 (warning) |
| Spread widening > 2x normal | -0.2 (liquidity concern) |

**Veto condition:** Volume > 5x normal AND price moving against miner consensus direction.

**Data sources:** Exchange APIs (Binance, Coinbase) for real-time volume/spread. Works with zero external API keys — needs only price/volume data.

**Env vars:** None required.

## Integration Points

### 1. App Lifespan (`trading/api/app.py`)

Initialize `IntelligenceLayer` during startup, subscribe to SignalBus:

```python
intel_layer = IntelligenceLayer(signal_bus=signal_bus, config=intel_config)
await intel_layer.start()
# on shutdown:
await intel_layer.stop()
```

### 2. BittensorSignalAgent (`trading/strategies/bittensor_signal.py`)

Modify `scan()` to:
- Read `intel_enriched_consensus` from SignalBus (or query IntelligenceLayer directly)
- Replace `confidence = min(abs(direction_score) * view.agreement_ratio, 1.0)` with enriched confidence
- Add gate 9 (veto check) after existing gates 1-8
- Include `intel_summary` in `Opportunity.data`

### 3. API Status (`trading/api/routes/bittensor.py`)

Add `intelligence` section to `/api/bittensor/status`:

```json
{
  "intelligence": {
    "enabled": true,
    "providers": {
      "on_chain": {"status": "healthy", "last_call_ms": 180, "circuit": "closed"},
      "sentiment": {"status": "healthy", "last_call_ms": 95, "circuit": "closed"},
      "anomaly": {"status": "healthy", "last_call_ms": 12, "circuit": "closed"}
    },
    "recent_enrichments": 47,
    "recent_vetos": 1,
    "avg_confidence_boost": 0.06
  }
}
```

### 4. Agent Config (`trading/agents/agents.yaml`)

New config keys on bittensor agents:

```yaml
bittensor_btc_5m:
  strategy: bittensor_signal
  parameters:
    intel_enabled: true
    intel_weights:
      on_chain: 0.15
      sentiment: 0.10
      anomaly: 0.05
    intel_veto_threshold: 1
```

### 5. Frontend Dashboard

Add intelligence health panel to Bittensor dashboard showing provider status, recent enrichments, veto count.

## Observability

```python
@dataclass
class IntelligenceMetrics:
    providers_called_total: int
    providers_failed: int
    vetos_issued: int
    enrichments_applied: int
    avg_provider_latency_ms: float
    p99_provider_latency_ms: float
    avg_confidence_boost: float
    max_confidence_boost: float
    veto_by_source: dict[str, int]
```

All events logged via existing `log_event()` with event types:
- `intel.enrichment` — confidence adjustment applied
- `intel.veto` — trade blocked by provider
- `intel.provider_error` — provider failed
- `intel.circuit_open` — circuit breaker tripped

## Backtestability

Store `IntelRecord` for every provider call. Replay during backtests:

```python
class IntelligenceReplay:
    async def replay(self, symbol: str, start: datetime, end: datetime):
        for record in self.store.get_range(symbol, start, end):
            yield record.report
```

Storage: Same PostgreSQL database, new `intel_records` table. 90-day retention in production.

## File Structure

```
trading/intelligence/
    __init__.py
    config.py                # IntelligenceConfig dataclass
    layer.py                 # IntelligenceLayer (orchestrator)
    models.py                # IntelReport, IntelEnrichment, IntelRecord
    circuit_breaker.py       # ProviderCircuitBreaker
    enrichment.py            # enrich_confidence() pure function
    providers/
        __init__.py
        base.py              # BaseIntelProvider ABC
        on_chain.py          # OnChainProvider
        sentiment.py         # SentimentProvider
        anomaly.py           # AnomalyProvider
    tests/
        test_layer.py
        test_enrichment.py
        test_circuit_breaker.py
        test_providers.py
```

## Testing Strategy

- **Unit tests:** Pure function tests for enrichment math, circuit breaker state machine, provider score logic with mocked API responses
- **Integration tests:** IntelligenceLayer with mocked providers, verifying SignalBus integration and timeout behavior
- **Provider tests:** Each provider tested with fixture data (recorded API responses)
- **Backtest validation:** Run enriched vs non-enriched signals against historical data, compare Sharpe ratios

## Out of Scope (v1)

- Negative alignment dampening (revisit with accuracy data)
- Provider weighting auto-tuning (manual weights first)
- Additional providers beyond the initial three
- Real-time provider accuracy tracking
- Frontend intel detail view (beyond status panel)
