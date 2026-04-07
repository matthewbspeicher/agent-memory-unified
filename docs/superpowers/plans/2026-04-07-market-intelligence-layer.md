# Market Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich Bittensor miner consensus signals with on-chain, sentiment, and anomaly intelligence to improve confidence calibration and block trades during extreme conditions.

**Architecture:** Three intel providers run in parallel behind circuit breakers, producing standardized `IntelReport` objects. An `IntelligenceLayer` orchestrator subscribes to `bittensor_consensus` signals on the SignalBus, gathers intel, enriches confidence via weighted alignment scores, and publishes `intel_enriched_consensus` signals. The `BittensorSignalAgent` reads enriched signals and applies a new veto gate (gate 9).

**Tech Stack:** Python 3.13, FastAPI, asyncio, aiohttp (HTTP clients), existing SignalBus/AgentSignal infrastructure, pytest + pytest-asyncio for tests.

**Spec:** `docs/superpowers/specs/2026-04-07-market-intelligence-layer-design.md`

---

## File Map

```
NEW FILES:
  trading/intelligence/__init__.py           — package init, re-exports
  trading/intelligence/models.py             — IntelReport, IntelEnrichment, IntelRecord dataclasses
  trading/intelligence/config.py             — IntelligenceConfig dataclass + STA_INTEL_* loading
  trading/intelligence/circuit_breaker.py    — ProviderCircuitBreaker state machine
  trading/intelligence/enrichment.py         — enrich_confidence() pure function
  trading/intelligence/providers/__init__.py  — provider package
  trading/intelligence/providers/base.py     — BaseIntelProvider ABC
  trading/intelligence/providers/on_chain.py — OnChainProvider
  trading/intelligence/providers/sentiment.py — SentimentProvider
  trading/intelligence/providers/anomaly.py  — AnomalyProvider
  trading/intelligence/layer.py              — IntelligenceLayer orchestrator
  trading/tests/unit/test_intel_models.py
  trading/tests/unit/test_intel_circuit_breaker.py
  trading/tests/unit/test_intel_enrichment.py
  trading/tests/unit/test_intel_providers.py
  trading/tests/unit/test_intel_layer.py

MODIFIED FILES:
  trading/config.py                          — add IntelligenceConfig, wire into Config + load_config
  trading/strategies/bittensor_signal.py     — add gate 9 (veto), use enriched confidence
  trading/api/app.py                         — init IntelligenceLayer in lifespan
  trading/api/routes/bittensor.py            — add intelligence section to /status
  trading/api/routes/bittensor_schemas.py    — add IntelligenceStatus schema
  trading/agents.yaml                        — add intel_* params to bittensor agents
```

---

### Task 1: Data Models

**Files:**
- Create: `trading/intelligence/__init__.py`
- Create: `trading/intelligence/models.py`
- Test: `trading/tests/unit/test_intel_models.py`

- [ ] **Step 1: Write failing test for IntelReport and IntelEnrichment**

```python
# trading/tests/unit/test_intel_models.py
import pytest
from datetime import datetime, timezone
from intelligence.models import IntelReport, IntelEnrichment, IntelRecord


def test_intel_report_creation():
    report = IntelReport(
        source="on_chain",
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=0.5,
        confidence=0.8,
        veto=False,
        veto_reason=None,
        details={"exchange_netflow": -1500.0},
    )
    assert report.source == "on_chain"
    assert report.score == 0.5
    assert report.veto is False


def test_intel_report_veto():
    report = IntelReport(
        source="anomaly",
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=-0.8,
        confidence=0.9,
        veto=True,
        veto_reason="Volume 5x normal against consensus",
        details={},
    )
    assert report.veto is True
    assert report.veto_reason == "Volume 5x normal against consensus"


def test_intel_enrichment_default():
    enrichment = IntelEnrichment(vetoed=False)
    assert enrichment.base_confidence == 0.0
    assert enrichment.adjustment == 0.0
    assert enrichment.final_confidence == 0.0
    assert enrichment.contributions == []


def test_intel_enrichment_vetoed():
    enrichment = IntelEnrichment(vetoed=True, veto_reason="dump signal")
    assert enrichment.vetoed is True
    assert enrichment.veto_reason == "dump signal"


def test_intel_record_creation():
    report = IntelReport(
        source="sentiment",
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=0.3,
        confidence=0.6,
        veto=False,
        veto_reason=None,
        details={},
    )
    record = IntelRecord(
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        provider="sentiment",
        report=report,
        latency_ms=95,
    )
    assert record.provider == "sentiment"
    assert record.latency_ms == 95
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/test_intel_models.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'intelligence'`

- [ ] **Step 3: Write the models**

```python
# trading/intelligence/__init__.py
"""Market Intelligence Layer — enriches Bittensor consensus signals."""

from intelligence.models import IntelReport, IntelEnrichment, IntelRecord

__all__ = ["IntelReport", "IntelEnrichment", "IntelRecord"]
```

```python
# trading/intelligence/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IntelReport:
    """Standardized output from any intelligence provider."""

    source: str          # "on_chain", "sentiment", "anomaly"
    symbol: str          # "BTCUSD"
    timestamp: datetime
    score: float         # -1.0 to +1.0 (bearish to bullish)
    confidence: float    # 0.0 to 1.0
    veto: bool           # True = hard block this trade
    veto_reason: str | None
    details: dict        # source-specific data


@dataclass
class IntelEnrichment:
    """Result of confidence enrichment calculation."""

    vetoed: bool
    veto_reason: str | None = None
    base_confidence: float = 0.0
    adjustment: float = 0.0
    final_confidence: float = 0.0
    contributions: list[dict] = field(default_factory=list)


@dataclass
class IntelRecord:
    """Stored for backtesting and analysis."""

    symbol: str
    timestamp: datetime
    provider: str
    report: IntelReport
    latency_ms: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && python -m pytest tests/unit/test_intel_models.py -v --tb=short`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add trading/intelligence/__init__.py trading/intelligence/models.py trading/tests/unit/test_intel_models.py
git commit -m "feat(intel): add IntelReport, IntelEnrichment, IntelRecord models"
```

---

### Task 2: Circuit Breaker

**Files:**
- Create: `trading/intelligence/circuit_breaker.py`
- Test: `trading/tests/unit/test_intel_circuit_breaker.py`

- [ ] **Step 1: Write failing tests**

```python
# trading/tests/unit/test_intel_circuit_breaker.py
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from intelligence.circuit_breaker import ProviderCircuitBreaker, CircuitOpenError


@pytest.mark.asyncio
async def test_circuit_starts_closed():
    cb = ProviderCircuitBreaker(failure_threshold=3, reset_timeout=60)
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_circuit_stays_closed_on_success():
    cb = ProviderCircuitBreaker(failure_threshold=3, reset_timeout=60)

    async def success():
        return "ok"

    result = await cb.call(success)
    assert result == "ok"
    assert cb.state == "closed"
    assert cb.failures == 0


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    cb = ProviderCircuitBreaker(failure_threshold=3, reset_timeout=60)

    async def fail():
        raise ValueError("boom")

    for _ in range(3):
        with pytest.raises(ValueError):
            await cb.call(fail)

    assert cb.state == "open"
    assert cb.failures == 3


@pytest.mark.asyncio
async def test_circuit_open_raises_circuit_open_error():
    cb = ProviderCircuitBreaker(failure_threshold=1, reset_timeout=60)

    async def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await cb.call(fail)

    assert cb.state == "open"

    with pytest.raises(CircuitOpenError):
        await cb.call(fail)


@pytest.mark.asyncio
async def test_circuit_resets_on_success_after_failure():
    cb = ProviderCircuitBreaker(failure_threshold=3, reset_timeout=60)

    async def fail():
        raise ValueError("boom")

    async def success():
        return "ok"

    # Two failures (below threshold)
    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.call(fail)

    assert cb.state == "closed"
    assert cb.failures == 2

    # One success resets
    result = await cb.call(success)
    assert result == "ok"
    assert cb.failures == 0


@pytest.mark.asyncio
async def test_circuit_half_open_after_reset_timeout():
    cb = ProviderCircuitBreaker(failure_threshold=1, reset_timeout=1)

    async def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await cb.call(fail)

    assert cb.state == "open"

    # Simulate time passing
    cb.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=2)

    async def success():
        return "recovered"

    result = await cb.call(success)
    assert result == "recovered"
    assert cb.state == "closed"
    assert cb.failures == 0


@pytest.mark.asyncio
async def test_circuit_half_open_failure_reopens():
    cb = ProviderCircuitBreaker(failure_threshold=1, reset_timeout=1)

    async def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await cb.call(fail)

    assert cb.state == "open"

    # Simulate time passing
    cb.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=2)

    # Half-open probe fails
    with pytest.raises(ValueError):
        await cb.call(fail)

    assert cb.state == "open"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/test_intel_circuit_breaker.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the circuit breaker**

```python
# trading/intelligence/circuit_breaker.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class CircuitOpenError(Exception):
    """Raised when a call is attempted on an open circuit."""


class ProviderCircuitBreaker:
    """Three-state circuit breaker: closed -> open -> half_open -> closed."""

    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures: int = 0
        self.state: str = "closed"
        self.last_failure_time: datetime | None = None

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        if self.state == "open":
            if self._should_attempt_reset():
                return await self._half_open_probe(func)
            raise CircuitOpenError(
                f"Circuit open, retry after {self.reset_timeout}s"
            )

        try:
            result = await func()
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
        return elapsed >= self.reset_timeout

    async def _half_open_probe(self, func: Callable[[], Awaitable[T]]) -> T:
        try:
            result = await func()
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self.failures = 0
        self.state = "closed"

    def _on_failure(self) -> None:
        self.failures += 1
        self.last_failure_time = datetime.now(timezone.utc)
        if self.failures >= self.failure_threshold:
            self.state = "open"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && python -m pytest tests/unit/test_intel_circuit_breaker.py -v --tb=short`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add trading/intelligence/circuit_breaker.py trading/tests/unit/test_intel_circuit_breaker.py
git commit -m "feat(intel): add ProviderCircuitBreaker with three-state machine"
```

---

### Task 3: Enrichment Pure Function

**Files:**
- Create: `trading/intelligence/enrichment.py`
- Test: `trading/tests/unit/test_intel_enrichment.py`

- [ ] **Step 1: Write failing tests**

```python
# trading/tests/unit/test_intel_enrichment.py
import pytest
from datetime import datetime, timezone
from intelligence.models import IntelReport
from intelligence.enrichment import enrich_confidence


def _make_report(source: str, score: float, confidence: float, veto: bool = False, veto_reason: str | None = None) -> IntelReport:
    return IntelReport(
        source=source,
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=score,
        confidence=confidence,
        veto=veto,
        veto_reason=veto_reason,
        details={},
    )


WEIGHTS = {"on_chain": 0.15, "sentiment": 0.10, "anomaly": 0.05}


def test_no_reports_returns_base():
    conf, enrichment = enrich_confidence(0.65, 0.5, [], WEIGHTS)
    assert conf == 0.65
    assert enrichment.vetoed is False
    assert enrichment.adjustment == 0.0


def test_aligned_report_boosts_confidence():
    # direction_score > 0, report score > 0 => alignment > 0 => boost
    reports = [_make_report("on_chain", score=0.6, confidence=0.8)]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf > 0.65
    assert enrichment.adjustment > 0.0
    assert len(enrichment.contributions) == 1
    assert enrichment.contributions[0]["source"] == "on_chain"


def test_conflicting_report_is_ignored():
    # direction_score > 0, report score < 0 => alignment < 0 => ignored in v1
    reports = [_make_report("sentiment", score=-0.5, confidence=0.9)]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf == 0.65
    assert enrichment.adjustment == 0.0
    assert len(enrichment.contributions) == 0


def test_veto_returns_zero_confidence():
    reports = [_make_report("anomaly", score=-0.8, confidence=0.9, veto=True, veto_reason="5x volume spike")]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf == 0.0
    assert enrichment.vetoed is True
    assert enrichment.veto_reason == "5x volume spike"


def test_adjustment_capped_at_30_percent():
    # All three aligned with max scores — should not exceed 30% boost
    reports = [
        _make_report("on_chain", score=1.0, confidence=1.0),
        _make_report("sentiment", score=1.0, confidence=1.0),
        _make_report("anomaly", score=1.0, confidence=1.0),
    ]
    conf, enrichment = enrich_confidence(0.50, 1.0, reports, WEIGHTS)
    max_allowed = 0.50 + (0.50 * 0.30)  # 0.65
    assert conf <= max_allowed + 0.001  # floating point tolerance
    assert conf > 0.50


def test_enrichment_clamps_to_one():
    # High base + aligned reports should not exceed 1.0
    reports = [_make_report("on_chain", score=1.0, confidence=1.0)]
    conf, enrichment = enrich_confidence(0.95, 1.0, reports, WEIGHTS)
    assert conf <= 1.0


def test_short_direction_with_bearish_intel():
    # direction_score < 0 (short), report score < 0 (bearish) => alignment > 0 => boost
    reports = [_make_report("on_chain", score=-0.6, confidence=0.8)]
    conf, enrichment = enrich_confidence(0.60, -0.5, reports, WEIGHTS)
    assert conf > 0.60
    assert enrichment.adjustment > 0.0


def test_unknown_source_gets_zero_weight():
    reports = [_make_report("unknown_source", score=1.0, confidence=1.0)]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf == 0.65
    assert enrichment.adjustment == 0.0


def test_zero_base_confidence():
    reports = [_make_report("on_chain", score=0.5, confidence=0.8)]
    conf, enrichment = enrich_confidence(0.0, 0.5, reports, WEIGHTS)
    # 30% of 0.0 = 0.0 cap, so no boost possible
    assert conf == 0.0


def test_veto_checked_before_enrichment():
    # Veto report first, then a boosting report — should still veto
    reports = [
        _make_report("anomaly", score=-0.9, confidence=0.95, veto=True, veto_reason="extreme volume"),
        _make_report("on_chain", score=0.8, confidence=0.9),
    ]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf == 0.0
    assert enrichment.vetoed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/test_intel_enrichment.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the enrichment function**

```python
# trading/intelligence/enrichment.py
from __future__ import annotations

import math
from intelligence.models import IntelReport, IntelEnrichment


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _sign(x: float) -> float:
    if x > 0:
        return 1.0
    elif x < 0:
        return -1.0
    return 0.0


def enrich_confidence(
    base_confidence: float,
    direction_score: float,
    reports: list[IntelReport],
    weights: dict[str, float],
    max_adjustment_pct: float = 0.30,
) -> tuple[float, IntelEnrichment]:
    """Enrich a base confidence score using intel reports.

    Returns (enriched_confidence, enrichment_details).
    """
    base_confidence = _clamp(base_confidence, 0.0, 1.0)
    total_adjustment = 0.0
    contributions: list[dict] = []

    for report in reports:
        if report.veto:
            return 0.0, IntelEnrichment(
                vetoed=True, veto_reason=report.veto_reason
            )

        alignment = report.score * _sign(direction_score)

        # v1: only boost on positive alignment
        if alignment > 0:
            weight = weights.get(report.source, 0.0)
            adjustment = alignment * report.confidence * weight
            total_adjustment += adjustment
            contributions.append({
                "source": report.source,
                "adjustment": adjustment,
                "alignment": alignment,
            })

    max_adjustment = base_confidence * max_adjustment_pct
    total_adjustment = _clamp(total_adjustment, -max_adjustment, max_adjustment)
    enriched = _clamp(base_confidence + total_adjustment, 0.0, 1.0)

    return enriched, IntelEnrichment(
        vetoed=False,
        base_confidence=base_confidence,
        adjustment=total_adjustment,
        final_confidence=enriched,
        contributions=contributions,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && python -m pytest tests/unit/test_intel_enrichment.py -v --tb=short`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add trading/intelligence/enrichment.py trading/tests/unit/test_intel_enrichment.py
git commit -m "feat(intel): add enrich_confidence pure function with 30% cap"
```

---

### Task 4: Provider Base Class and Config

**Files:**
- Create: `trading/intelligence/providers/__init__.py`
- Create: `trading/intelligence/providers/base.py`
- Create: `trading/intelligence/config.py`
- Modify: `trading/config.py` — add `IntelligenceConfig` and wire into `Config` + `load_config`

- [ ] **Step 1: Write the base provider and config**

```python
# trading/intelligence/providers/__init__.py
"""Intelligence providers package."""
```

```python
# trading/intelligence/providers/base.py
from __future__ import annotations

import abc
from intelligence.models import IntelReport


class BaseIntelProvider(abc.ABC):
    """Abstract base for all intelligence providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'on_chain', 'sentiment', 'anomaly')."""

    @abc.abstractmethod
    async def analyze(self, symbol: str) -> IntelReport | None:
        """Analyze the given symbol and return an IntelReport, or None if unavailable."""
```

```python
# trading/intelligence/config.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IntelligenceConfig:
    """Configuration for the Market Intelligence Layer."""

    enabled: bool = False
    timeout_ms: int = 2000
    min_providers: int = 1
    veto_threshold: int = 1  # 1=any, 2=majority
    weights: dict[str, float] = field(default_factory=lambda: {
        "on_chain": 0.15,
        "sentiment": 0.10,
        "anomaly": 0.05,
    })
    max_adjustment_pct: float = 0.30
    stale_data_threshold_seconds: int = 300
    circuit_breaker_failures: int = 3
    circuit_breaker_reset_seconds: int = 60

    # API keys (all optional — providers degrade gracefully)
    coinglass_api_key: str | None = None
    glassnode_api_key: str | None = None
    lunarcrush_api_key: str | None = None
    santiment_api_key: str | None = None
```

- [ ] **Step 2: Add IntelligenceConfig to Config and load_config**

Modify `trading/config.py`:

Add import at top:
```python
from intelligence.config import IntelligenceConfig
```

Add field to `Config` dataclass (after `bittensor` field, line ~87):
```python
    intel: IntelligenceConfig = field(default_factory=IntelligenceConfig)
```

Add to `load_config()` function, after the `bt_annotations` line (~365):
```python
    intel_annotations = IntelligenceConfig.__annotations__
```

Add parsing block inside the `for field_name, raw_value in config_dict.items():` loop, after the bittensor block (~379):
```python
        if field_name.startswith("intel_"):
            nested_name = field_name[len("intel_"):]
            if nested_name in intel_annotations:
                _set_nested(
                    config.intel,
                    nested_name,
                    raw_value,
                    intel_annotations[nested_name],
                )
                continue
```

- [ ] **Step 3: Write test for config loading**

```python
# Add to trading/tests/unit/test_intel_models.py (append to existing file)

def test_intelligence_config_defaults():
    from intelligence.config import IntelligenceConfig

    cfg = IntelligenceConfig()
    assert cfg.enabled is False
    assert cfg.timeout_ms == 2000
    assert cfg.veto_threshold == 1
    assert cfg.weights == {"on_chain": 0.15, "sentiment": 0.10, "anomaly": 0.05}
    assert cfg.max_adjustment_pct == 0.30


def test_intelligence_config_from_env(monkeypatch):
    monkeypatch.setenv("STA_INTEL_ENABLED", "true")
    monkeypatch.setenv("STA_INTEL_TIMEOUT_MS", "3000")
    monkeypatch.setenv("STA_INTEL_VETO_THRESHOLD", "2")
    monkeypatch.setenv("STA_INTEL_COINGLASS_API_KEY", "test-key-123")

    from config import load_config

    cfg = load_config(env_file="/dev/null")
    assert cfg.intel.enabled is True
    assert cfg.intel.timeout_ms == 3000
    assert cfg.intel.veto_threshold == 2
    assert cfg.intel.coinglass_api_key == "test-key-123"
```

- [ ] **Step 4: Run tests**

Run: `cd trading && python -m pytest tests/unit/test_intel_models.py -v --tb=short`
Expected: 7 passed (5 original + 2 new)

- [ ] **Step 5: Commit**

```bash
git add trading/intelligence/providers/__init__.py trading/intelligence/providers/base.py trading/intelligence/config.py trading/config.py trading/tests/unit/test_intel_models.py
git commit -m "feat(intel): add BaseIntelProvider ABC, IntelligenceConfig, wire into Config"
```

---

### Task 5: SentimentProvider

**Files:**
- Create: `trading/intelligence/providers/sentiment.py`
- Test: `trading/tests/unit/test_intel_providers.py`

Starting with Sentiment because it uses the free Alternative.me API (no key needed) — easiest to test.

- [ ] **Step 1: Write failing tests**

```python
# trading/tests/unit/test_intel_providers.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from intelligence.providers.sentiment import SentimentProvider


@pytest.mark.asyncio
async def test_sentiment_extreme_fear():
    """Fear & Greed < 25 => contrarian bullish score."""
    provider = SentimentProvider()

    with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, return_value=15):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.source == "sentiment"
    assert report.score > 0  # contrarian bullish
    assert report.veto is False


@pytest.mark.asyncio
async def test_sentiment_extreme_greed():
    """Fear & Greed > 75 => contrarian bearish score."""
    provider = SentimentProvider()

    with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, return_value=85):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.score < 0  # contrarian bearish
    assert report.veto is False


@pytest.mark.asyncio
async def test_sentiment_neutral():
    """Fear & Greed ~50 => near-zero score."""
    provider = SentimentProvider()

    with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, return_value=50):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert abs(report.score) < 0.1


@pytest.mark.asyncio
async def test_sentiment_api_failure_returns_none():
    provider = SentimentProvider()

    with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, side_effect=Exception("API down")):
        report = await provider.analyze("BTCUSD")

    assert report is None


@pytest.mark.asyncio
async def test_sentiment_never_vetoes():
    """Sentiment provider should never veto — too noisy."""
    provider = SentimentProvider()

    for value in [0, 10, 50, 90, 100]:
        with patch.object(provider, "_fetch_fear_greed", new_callable=AsyncMock, return_value=value):
            report = await provider.analyze("BTCUSD")
        if report is not None:
            assert report.veto is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/test_intel_providers.py::test_sentiment_extreme_fear -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write SentimentProvider**

```python
# trading/intelligence/providers/sentiment.py
from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

logger = logging.getLogger(__name__)


class SentimentProvider(BaseIntelProvider):
    """Reads Crypto Fear & Greed Index from Alternative.me (free, no key)."""

    @property
    def name(self) -> str:
        return "sentiment"

    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            fg_value = await self._fetch_fear_greed()
        except Exception as e:
            logger.warning("SentimentProvider failed: %s", e)
            return None

        score = self._fg_to_score(fg_value)
        confidence = self._fg_to_confidence(fg_value)

        return IntelReport(
            source=self.name,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=score,
            confidence=confidence,
            veto=False,
            veto_reason=None,
            details={"fear_greed_value": fg_value},
        )

    async def _fetch_fear_greed(self) -> int:
        """Fetch current Fear & Greed Index. Override in tests."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.alternative.me/fng/?limit=1", timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                data = await resp.json()
                return int(data["data"][0]["value"])

    @staticmethod
    def _fg_to_score(value: int) -> float:
        """Convert Fear & Greed (0-100) to score (-1 to +1), contrarian.

        Extreme fear (0-25) -> bullish (+0.2 to +0.5)
        Neutral (25-75) -> near zero
        Extreme greed (75-100) -> bearish (-0.2 to -0.5)
        """
        # Linear mapping: 0 -> +0.5, 50 -> 0.0, 100 -> -0.5
        return (50 - value) / 100.0

    @staticmethod
    def _fg_to_confidence(value: int) -> float:
        """Confidence is higher at extremes, lower near neutral."""
        distance_from_center = abs(value - 50)
        # 0 at center, 1.0 at extremes
        return min(distance_from_center / 50.0, 1.0) * 0.7 + 0.3
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && python -m pytest tests/unit/test_intel_providers.py -v --tb=short`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add trading/intelligence/providers/sentiment.py trading/tests/unit/test_intel_providers.py
git commit -m "feat(intel): add SentimentProvider with Fear & Greed contrarian scoring"
```

---

### Task 6: OnChainProvider

**Files:**
- Create: `trading/intelligence/providers/on_chain.py`
- Modify: `trading/tests/unit/test_intel_providers.py` — add on-chain tests

- [ ] **Step 1: Write failing tests**

Append to `trading/tests/unit/test_intel_providers.py`:

```python
from intelligence.providers.on_chain import OnChainProvider


@pytest.mark.asyncio
async def test_on_chain_accumulation_bullish():
    """Net exchange outflow => bullish score."""
    provider = OnChainProvider()

    with patch.object(provider, "_fetch_exchange_netflow", new_callable=AsyncMock, return_value=-5000.0):
        with patch.object(provider, "_fetch_exchange_netflow_30d_avg", new_callable=AsyncMock, return_value=2000.0):
            report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.source == "on_chain"
    assert report.score > 0  # outflow = bullish
    assert report.veto is False


@pytest.mark.asyncio
async def test_on_chain_distribution_bearish():
    """Net exchange inflow => bearish score."""
    provider = OnChainProvider()

    with patch.object(provider, "_fetch_exchange_netflow", new_callable=AsyncMock, return_value=3000.0):
        with patch.object(provider, "_fetch_exchange_netflow_30d_avg", new_callable=AsyncMock, return_value=2000.0):
            report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.score < 0  # inflow = bearish
    assert report.veto is False


@pytest.mark.asyncio
async def test_on_chain_veto_on_massive_inflow():
    """Exchange inflow > 2x 30-day average => veto."""
    provider = OnChainProvider()

    with patch.object(provider, "_fetch_exchange_netflow", new_callable=AsyncMock, return_value=5000.0):
        with patch.object(provider, "_fetch_exchange_netflow_30d_avg", new_callable=AsyncMock, return_value=2000.0):
            report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.veto is True
    assert "2x" in report.veto_reason.lower() or "exchange inflow" in report.veto_reason.lower()


@pytest.mark.asyncio
async def test_on_chain_no_api_key_returns_none():
    provider = OnChainProvider(coinglass_api_key=None)

    with patch.object(provider, "_fetch_exchange_netflow", new_callable=AsyncMock, side_effect=Exception("No API key")):
        report = await provider.analyze("BTCUSD")

    assert report is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/test_intel_providers.py::test_on_chain_accumulation_bullish -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write OnChainProvider**

```python
# trading/intelligence/providers/on_chain.py
from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

logger = logging.getLogger(__name__)


class OnChainProvider(BaseIntelProvider):
    """Reads exchange netflow data to gauge accumulation vs distribution."""

    def __init__(self, coinglass_api_key: str | None = None):
        self.coinglass_api_key = coinglass_api_key

    @property
    def name(self) -> str:
        return "on_chain"

    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            netflow = await self._fetch_exchange_netflow(symbol)
            avg_30d = await self._fetch_exchange_netflow_30d_avg(symbol)
        except Exception as e:
            logger.warning("OnChainProvider failed for %s: %s", symbol, e)
            return None

        score = self._netflow_to_score(netflow, avg_30d)
        confidence = self._netflow_to_confidence(netflow, avg_30d)
        veto, veto_reason = self._check_veto(netflow, avg_30d)

        return IntelReport(
            source=self.name,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=score,
            confidence=confidence,
            veto=veto,
            veto_reason=veto_reason,
            details={
                "exchange_netflow": netflow,
                "avg_30d_netflow": avg_30d,
            },
        )

    async def _fetch_exchange_netflow(self, symbol: str = "BTCUSD") -> float:
        """Fetch current exchange netflow. Positive = inflow, negative = outflow."""
        import aiohttp

        if not self.coinglass_api_key:
            raise ValueError("No CoinGlass API key configured")

        coin = symbol[:3]  # "BTCUSD" -> "BTC"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://open-api-v3.coinglass.com/api/indicator/exchange/netflow-total",
                params={"coin": coin, "range": "1d"},
                headers={"CG-API-KEY": self.coinglass_api_key},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                return float(data.get("data", [{}])[-1].get("value", 0.0))

    async def _fetch_exchange_netflow_30d_avg(self, symbol: str = "BTCUSD") -> float:
        """Fetch 30-day average netflow for comparison."""
        import aiohttp

        if not self.coinglass_api_key:
            raise ValueError("No CoinGlass API key configured")

        coin = symbol[:3]
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://open-api-v3.coinglass.com/api/indicator/exchange/netflow-total",
                params={"coin": coin, "range": "30d"},
                headers={"CG-API-KEY": self.coinglass_api_key},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                values = [float(d.get("value", 0.0)) for d in data.get("data", [])]
                if not values:
                    return 0.0
                return sum(values) / len(values)

    @staticmethod
    def _netflow_to_score(netflow: float, avg_30d: float) -> float:
        """Negative netflow (outflow/accumulation) -> positive score (bullish).
        Positive netflow (inflow/distribution) -> negative score (bearish).
        Normalized against 30-day average.
        """
        if avg_30d == 0:
            return 0.0
        ratio = netflow / abs(avg_30d)
        # Clamp ratio to [-1, 1] range, then invert (outflow = bullish)
        clamped = max(-1.0, min(1.0, ratio))
        return -clamped * 0.5  # scale to [-0.5, 0.5]

    @staticmethod
    def _netflow_to_confidence(netflow: float, avg_30d: float) -> float:
        if avg_30d == 0:
            return 0.3
        deviation = abs(netflow) / abs(avg_30d)
        # Higher deviation = higher confidence
        return min(0.3 + deviation * 0.3, 1.0)

    @staticmethod
    def _check_veto(netflow: float, avg_30d: float) -> tuple[bool, str | None]:
        """Veto if exchange inflow exceeds 2x 30-day average."""
        if avg_30d == 0:
            return False, None
        if netflow > 0 and netflow > abs(avg_30d) * 2.0:
            return True, f"Exchange inflow {netflow:.0f} exceeds 2x 30d avg ({abs(avg_30d):.0f})"
        return False, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && python -m pytest tests/unit/test_intel_providers.py -v --tb=short`
Expected: 9 passed (5 sentiment + 4 on-chain)

- [ ] **Step 5: Commit**

```bash
git add trading/intelligence/providers/on_chain.py trading/tests/unit/test_intel_providers.py
git commit -m "feat(intel): add OnChainProvider with exchange netflow scoring + veto"
```

---

### Task 7: AnomalyProvider

**Files:**
- Create: `trading/intelligence/providers/anomaly.py`
- Modify: `trading/tests/unit/test_intel_providers.py` — add anomaly tests

- [ ] **Step 1: Write failing tests**

Append to `trading/tests/unit/test_intel_providers.py`:

```python
from intelligence.providers.anomaly import AnomalyProvider


@pytest.mark.asyncio
async def test_anomaly_high_volume_aligned():
    """Volume 3x normal + price aligned with direction => confirms direction."""
    provider = AnomalyProvider()

    with patch.object(provider, "_fetch_volume_ratio", new_callable=AsyncMock, return_value=3.5):
        with patch.object(provider, "_fetch_price_direction", new_callable=AsyncMock, return_value=1.0):
            with patch.object(provider, "_fetch_spread_ratio", new_callable=AsyncMock, return_value=1.0):
                report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.source == "anomaly"
    assert report.score > 0  # volume confirms bullish price
    assert report.veto is False


@pytest.mark.asyncio
async def test_anomaly_high_volume_diverges():
    """Volume 3x normal + price diverges => warning."""
    provider = AnomalyProvider()

    with patch.object(provider, "_fetch_volume_ratio", new_callable=AsyncMock, return_value=3.5):
        with patch.object(provider, "_fetch_price_direction", new_callable=AsyncMock, return_value=-1.0):
            with patch.object(provider, "_fetch_spread_ratio", new_callable=AsyncMock, return_value=1.0):
                report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.score < 0  # divergence warning


@pytest.mark.asyncio
async def test_anomaly_veto_extreme_volume():
    """Volume > 5x normal + price against consensus => veto."""
    provider = AnomalyProvider()

    with patch.object(provider, "_fetch_volume_ratio", new_callable=AsyncMock, return_value=6.0):
        with patch.object(provider, "_fetch_price_direction", new_callable=AsyncMock, return_value=-1.0):
            with patch.object(provider, "_fetch_spread_ratio", new_callable=AsyncMock, return_value=1.5):
                report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.veto is True


@pytest.mark.asyncio
async def test_anomaly_normal_conditions():
    """Normal volume, normal spread => near-zero score, no veto."""
    provider = AnomalyProvider()

    with patch.object(provider, "_fetch_volume_ratio", new_callable=AsyncMock, return_value=1.2):
        with patch.object(provider, "_fetch_price_direction", new_callable=AsyncMock, return_value=0.5):
            with patch.object(provider, "_fetch_spread_ratio", new_callable=AsyncMock, return_value=1.0):
                report = await provider.analyze("BTCUSD")

    assert report is not None
    assert abs(report.score) < 0.15
    assert report.veto is False


@pytest.mark.asyncio
async def test_anomaly_api_failure_returns_none():
    provider = AnomalyProvider()

    with patch.object(provider, "_fetch_volume_ratio", new_callable=AsyncMock, side_effect=Exception("exchange down")):
        report = await provider.analyze("BTCUSD")

    assert report is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/test_intel_providers.py::test_anomaly_high_volume_aligned -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write AnomalyProvider**

```python
# trading/intelligence/providers/anomaly.py
from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

logger = logging.getLogger(__name__)


class AnomalyProvider(BaseIntelProvider):
    """Detects anomalies via volume deviation, price-volume divergence, spread widening."""

    @property
    def name(self) -> str:
        return "anomaly"

    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            volume_ratio = await self._fetch_volume_ratio(symbol)
            price_direction = await self._fetch_price_direction(symbol)
            spread_ratio = await self._fetch_spread_ratio(symbol)
        except Exception as e:
            logger.warning("AnomalyProvider failed for %s: %s", symbol, e)
            return None

        score = self._compute_score(volume_ratio, price_direction, spread_ratio)
        confidence = self._compute_confidence(volume_ratio, spread_ratio)
        veto, veto_reason = self._check_veto(volume_ratio, price_direction)

        return IntelReport(
            source=self.name,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=score,
            confidence=confidence,
            veto=veto,
            veto_reason=veto_reason,
            details={
                "volume_ratio": volume_ratio,
                "price_direction": price_direction,
                "spread_ratio": spread_ratio,
            },
        )

    async def _fetch_volume_ratio(self, symbol: str) -> float:
        """Current volume / 20-period average volume. Override in tests."""
        raise NotImplementedError("Requires exchange API integration")

    async def _fetch_price_direction(self, symbol: str) -> float:
        """Recent price movement: +1 = up, -1 = down, 0 = flat. Override in tests."""
        raise NotImplementedError("Requires exchange API integration")

    async def _fetch_spread_ratio(self, symbol: str) -> float:
        """Current spread / average spread. >1 = widening. Override in tests."""
        raise NotImplementedError("Requires exchange API integration")

    @staticmethod
    def _compute_score(volume_ratio: float, price_direction: float, spread_ratio: float) -> float:
        score = 0.0

        # High volume + aligned price = confirms direction
        if volume_ratio >= 3.0:
            score += price_direction * 0.2
        elif volume_ratio >= 2.0:
            score += price_direction * 0.1

        # Spread widening = liquidity concern
        if spread_ratio > 2.0:
            score -= 0.2
        elif spread_ratio > 1.5:
            score -= 0.1

        return max(-1.0, min(1.0, score))

    @staticmethod
    def _compute_confidence(volume_ratio: float, spread_ratio: float) -> float:
        # More extreme conditions = higher confidence in the anomaly reading
        volume_conf = min((volume_ratio - 1.0) / 4.0, 0.5) if volume_ratio > 1.0 else 0.0
        spread_conf = min((spread_ratio - 1.0) / 2.0, 0.3) if spread_ratio > 1.0 else 0.0
        return min(0.3 + volume_conf + spread_conf, 1.0)

    @staticmethod
    def _check_veto(volume_ratio: float, price_direction: float) -> tuple[bool, str | None]:
        """Veto if volume > 5x normal AND price moving against (likely manipulation/black swan)."""
        if volume_ratio > 5.0 and price_direction < 0:
            return True, f"Volume {volume_ratio:.1f}x normal with price declining — possible manipulation"
        return False, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && python -m pytest tests/unit/test_intel_providers.py -v --tb=short`
Expected: 14 passed (5 sentiment + 4 on-chain + 5 anomaly)

- [ ] **Step 5: Commit**

```bash
git add trading/intelligence/providers/anomaly.py trading/tests/unit/test_intel_providers.py
git commit -m "feat(intel): add AnomalyProvider with volume/spread/divergence detection"
```

---

### Task 8: IntelligenceLayer Orchestrator

**Files:**
- Create: `trading/intelligence/layer.py`
- Test: `trading/tests/unit/test_intel_layer.py`

- [ ] **Step 1: Write failing tests**

```python
# trading/tests/unit/test_intel_layer.py
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from agents.models import AgentSignal
from data.signal_bus import SignalBus
from intelligence.config import IntelligenceConfig
from intelligence.models import IntelReport
from intelligence.layer import IntelligenceLayer


def _make_report(source: str, score: float, confidence: float, veto: bool = False, veto_reason: str | None = None) -> IntelReport:
    return IntelReport(
        source=source,
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=score,
        confidence=confidence,
        veto=veto,
        veto_reason=veto_reason,
        details={},
    )


def _make_consensus_signal(symbol: str = "BTCUSD", direction: str = "bullish", confidence: float = 0.8) -> AgentSignal:
    return AgentSignal(
        source_agent="miner_consensus_aggregator",
        signal_type="bittensor_consensus",
        payload={
            "symbol": symbol,
            "timeframe": "5m",
            "direction": direction,
            "confidence": confidence,
            "expected_return": 0.003,
            "window_id": "20260407-1200",
            "miner_count": 5,
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )


@pytest.mark.asyncio
async def test_layer_enriches_consensus_signal():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=True)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    # Mock providers
    layer._on_chain = MagicMock()
    layer._on_chain.analyze = AsyncMock(return_value=_make_report("on_chain", 0.5, 0.8))
    layer._sentiment = MagicMock()
    layer._sentiment.analyze = AsyncMock(return_value=_make_report("sentiment", 0.3, 0.6))
    layer._anomaly = MagicMock()
    layer._anomaly.analyze = AsyncMock(return_value=_make_report("anomaly", 0.1, 0.5))

    published = []
    original_publish = signal_bus.publish

    async def capture_publish(signal: AgentSignal):
        published.append(signal)
        await original_publish(signal)

    signal_bus.publish = capture_publish

    await layer.start()
    consensus = _make_consensus_signal()
    await layer._handle_consensus(consensus)

    # Should have published an intel_enriched_consensus signal
    enriched = [s for s in published if s.signal_type == "intel_enriched_consensus"]
    assert len(enriched) == 1
    payload = enriched[0].payload
    assert payload["symbol"] == "BTCUSD"
    assert "enriched_confidence" in payload
    assert payload["enriched_confidence"] >= consensus.payload["confidence"]
    assert payload["vetoed"] is False

    await layer.stop()


@pytest.mark.asyncio
async def test_layer_veto_blocks_signal():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=True)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    layer._on_chain = MagicMock()
    layer._on_chain.analyze = AsyncMock(return_value=_make_report("on_chain", -0.8, 0.9, veto=True, veto_reason="massive inflow"))
    layer._sentiment = MagicMock()
    layer._sentiment.analyze = AsyncMock(return_value=_make_report("sentiment", 0.2, 0.5))
    layer._anomaly = MagicMock()
    layer._anomaly.analyze = AsyncMock(return_value=_make_report("anomaly", 0.0, 0.3))

    published = []

    async def capture_publish(signal: AgentSignal):
        published.append(signal)

    signal_bus.publish = capture_publish

    await layer.start()
    await layer._handle_consensus(_make_consensus_signal())

    enriched = [s for s in published if s.signal_type == "intel_enriched_consensus"]
    assert len(enriched) == 1
    assert enriched[0].payload["vetoed"] is True
    assert enriched[0].payload["enriched_confidence"] == 0.0

    await layer.stop()


@pytest.mark.asyncio
async def test_layer_handles_all_providers_failing():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=True)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    layer._on_chain = MagicMock()
    layer._on_chain.analyze = AsyncMock(side_effect=Exception("fail"))
    layer._sentiment = MagicMock()
    layer._sentiment.analyze = AsyncMock(side_effect=Exception("fail"))
    layer._anomaly = MagicMock()
    layer._anomaly.analyze = AsyncMock(side_effect=Exception("fail"))

    published = []

    async def capture_publish(signal: AgentSignal):
        published.append(signal)

    signal_bus.publish = capture_publish

    await layer.start()
    await layer._handle_consensus(_make_consensus_signal(confidence=0.75))

    # Should still publish with original confidence (passthrough)
    enriched = [s for s in published if s.signal_type == "intel_enriched_consensus"]
    assert len(enriched) == 1
    assert enriched[0].payload["enriched_confidence"] == 0.75
    assert enriched[0].payload["vetoed"] is False

    await layer.stop()


@pytest.mark.asyncio
async def test_layer_get_status():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=True)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    status = layer.get_status()
    assert status["enabled"] is True
    assert "providers" in status
    assert "on_chain" in status["providers"]
    assert "sentiment" in status["providers"]
    assert "anomaly" in status["providers"]


@pytest.mark.asyncio
async def test_layer_disabled_passthrough():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=False)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    published = []

    async def capture_publish(signal: AgentSignal):
        published.append(signal)

    signal_bus.publish = capture_publish

    await layer.start()
    await layer._handle_consensus(_make_consensus_signal(confidence=0.65))

    # When disabled, should still publish passthrough
    enriched = [s for s in published if s.signal_type == "intel_enriched_consensus"]
    assert len(enriched) == 1
    assert enriched[0].payload["enriched_confidence"] == 0.65
    assert enriched[0].payload["vetoed"] is False

    await layer.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/test_intel_layer.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write IntelligenceLayer**

```python
# trading/intelligence/layer.py
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from agents.models import AgentSignal
from data.signal_bus import SignalBus
from intelligence.circuit_breaker import ProviderCircuitBreaker, CircuitOpenError
from intelligence.config import IntelligenceConfig
from intelligence.enrichment import enrich_confidence
from intelligence.models import IntelReport
from intelligence.providers.anomaly import AnomalyProvider
from intelligence.providers.on_chain import OnChainProvider
from intelligence.providers.sentiment import SentimentProvider
from utils.logging import log_event

logger = logging.getLogger(__name__)


class IntelligenceLayer:
    """Orchestrates intel providers, enriches consensus signals, publishes results."""

    def __init__(self, signal_bus: SignalBus, config: IntelligenceConfig):
        self.signal_bus = signal_bus
        self.config = config
        self._running = False

        # Providers
        self._on_chain = OnChainProvider(coinglass_api_key=config.coinglass_api_key)
        self._sentiment = SentimentProvider()
        self._anomaly = AnomalyProvider()

        # Circuit breakers (one per provider)
        self._breakers: dict[str, ProviderCircuitBreaker] = {
            "on_chain": ProviderCircuitBreaker(config.circuit_breaker_failures, config.circuit_breaker_reset_seconds),
            "sentiment": ProviderCircuitBreaker(config.circuit_breaker_failures, config.circuit_breaker_reset_seconds),
            "anomaly": ProviderCircuitBreaker(config.circuit_breaker_failures, config.circuit_breaker_reset_seconds),
        }

        # Metrics
        self._enrichments_applied = 0
        self._vetos_issued = 0
        self._provider_failures = 0
        self._total_calls = 0

    async def start(self) -> None:
        self._running = True
        self.signal_bus.subscribe(self._handle_consensus)
        logger.info("IntelligenceLayer started (enabled=%s)", self.config.enabled)

    async def stop(self) -> None:
        self._running = False

    async def _handle_consensus(self, signal: AgentSignal) -> None:
        if signal.signal_type != "bittensor_consensus":
            return
        if not self._running:
            return

        payload = signal.payload
        symbol = payload.get("symbol", "BTCUSD")
        base_confidence = payload.get("confidence", 0.0)
        direction = payload.get("direction", "flat")

        # Map direction to numeric score for enrichment
        direction_score = {"bullish": 1.0, "bearish": -1.0, "flat": 0.0}.get(direction, 0.0)

        if not self.config.enabled:
            await self._publish_enriched(signal, base_confidence, vetoed=False, enrichment_data={})
            return

        reports = await self._gather_intel(symbol)

        enriched_confidence, enrichment = enrich_confidence(
            base_confidence=base_confidence,
            direction_score=direction_score,
            reports=reports,
            weights=self.config.weights,
            max_adjustment_pct=self.config.max_adjustment_pct,
        )

        if enrichment.vetoed:
            self._vetos_issued += 1
            log_event(logger, logging.WARNING, "intel.veto", f"Intel veto for {symbol}: {enrichment.veto_reason}", data={"symbol": symbol, "reason": enrichment.veto_reason})
        else:
            self._enrichments_applied += 1
            log_event(logger, logging.INFO, "intel.enrichment", f"Intel enrichment for {symbol}: {base_confidence:.3f} -> {enriched_confidence:.3f}", data={"symbol": symbol, "base": base_confidence, "enriched": enriched_confidence, "adjustment": enrichment.adjustment})

        await self._publish_enriched(
            signal,
            enriched_confidence,
            vetoed=enrichment.vetoed,
            enrichment_data={
                "veto_reason": enrichment.veto_reason,
                "base_confidence": enrichment.base_confidence,
                "adjustment": enrichment.adjustment,
                "contributions": enrichment.contributions,
            },
        )

    async def _gather_intel(self, symbol: str) -> list[IntelReport]:
        providers = [
            ("on_chain", self._on_chain),
            ("sentiment", self._sentiment),
            ("anomaly", self._anomaly),
        ]

        async def _call_provider(name: str, provider) -> IntelReport | None:
            self._total_calls += 1
            breaker = self._breakers[name]
            try:
                return await breaker.call(lambda: provider.analyze(symbol))
            except CircuitOpenError:
                logger.debug("Circuit open for provider %s, skipping", name)
                return None
            except Exception as e:
                self._provider_failures += 1
                logger.warning("Intel provider %s failed: %s", name, e)
                return None

        timeout = self.config.timeout_ms / 1000.0
        tasks = [_call_provider(name, provider) for name, provider in providers]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Intelligence gathering timed out after %dms", self.config.timeout_ms)
            return []

        reports = []
        for result in results:
            if isinstance(result, IntelReport):
                if result.veto:
                    return [result]  # early exit on veto
                reports.append(result)

        return reports

    async def _publish_enriched(self, original: AgentSignal, enriched_confidence: float, vetoed: bool, enrichment_data: dict) -> None:
        enriched_payload = dict(original.payload)
        enriched_payload["enriched_confidence"] = enriched_confidence
        enriched_payload["vetoed"] = vetoed
        enriched_payload["intel"] = enrichment_data

        enriched_signal = AgentSignal(
            source_agent="intelligence_layer",
            signal_type="intel_enriched_consensus",
            payload=enriched_payload,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        await self.signal_bus.publish(enriched_signal)

    def get_status(self) -> dict:
        return {
            "enabled": self.config.enabled,
            "providers": {
                name: {
                    "circuit": breaker.state,
                    "failures": breaker.failures,
                }
                for name, breaker in self._breakers.items()
            },
            "enrichments_applied": self._enrichments_applied,
            "vetos_issued": self._vetos_issued,
            "provider_failures": self._provider_failures,
            "total_calls": self._total_calls,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && python -m pytest tests/unit/test_intel_layer.py -v --tb=short`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add trading/intelligence/layer.py trading/tests/unit/test_intel_layer.py
git commit -m "feat(intel): add IntelligenceLayer orchestrator with circuit breakers + metrics"
```

---

### Task 9: Wire into App Lifespan

**Files:**
- Modify: `trading/api/app.py` (~line 491, after MinerConsensusAggregator start)

- [ ] **Step 1: Add IntelligenceLayer initialization**

After the `logger.info("MinerConsensusAggregator started")` line (~494 in `trading/api/app.py`), add:

```python
        # Intelligence Layer
        from intelligence.layer import IntelligenceLayer

        intel_layer = IntelligenceLayer(
            signal_bus=signal_bus,
            config=settings.intel,
        )
        app.state.intelligence_layer = intel_layer
        task_mgr.create_task(intel_layer.start(), name="intelligence_layer")
        logger.info("IntelligenceLayer started (enabled=%s)", settings.intel.enabled)
```

- [ ] **Step 2: Verify app imports work**

Run: `cd trading && python -c "from intelligence.layer import IntelligenceLayer; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add trading/api/app.py
git commit -m "feat(intel): wire IntelligenceLayer into app lifespan"
```

---

### Task 10: Add Gate 9 to BittensorSignalAgent

**Files:**
- Modify: `trading/strategies/bittensor_signal.py`

- [ ] **Step 1: Write a test for the veto gate**

Append to existing test file or create new. Since `BittensorSignalAgent` uses `DataBus`, we test the gate logic directly:

```python
# trading/tests/unit/test_intel_gate.py
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from agents.models import AgentSignal
from data.signal_bus import SignalBus


def test_enriched_signal_with_veto_payload():
    """Verify the enriched signal structure carries veto info for gate 9."""
    payload = {
        "symbol": "BTCUSD",
        "timeframe": "5m",
        "direction": "bullish",
        "confidence": 0.0,
        "expected_return": 0.003,
        "window_id": "20260407-1200",
        "miner_count": 5,
        "enriched_confidence": 0.0,
        "vetoed": True,
        "intel": {"veto_reason": "massive dump detected"},
    }
    signal = AgentSignal(
        source_agent="intelligence_layer",
        signal_type="intel_enriched_consensus",
        payload=payload,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    assert signal.payload["vetoed"] is True
    assert signal.payload["enriched_confidence"] == 0.0


def test_enriched_signal_with_boost():
    payload = {
        "symbol": "BTCUSD",
        "enriched_confidence": 0.78,
        "vetoed": False,
        "intel": {"base_confidence": 0.65, "adjustment": 0.13},
    }
    signal = AgentSignal(
        source_agent="intelligence_layer",
        signal_type="intel_enriched_consensus",
        payload=payload,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    assert signal.payload["vetoed"] is False
    assert signal.payload["enriched_confidence"] == 0.78
```

- [ ] **Step 2: Modify BittensorSignalAgent.scan()**

In `trading/strategies/bittensor_signal.py`, after the existing gate 8 (short signals gate, ~line 89) and before the `# Derive signal` comment (~line 92):

Add gate 9:

```python
        # Gate: intel veto
        intel_enabled = self.parameters.get("intel_enabled", False)
        intel_enrichment = None
        if intel_enabled:
            signal_bus = getattr(data, "_signal_bus", None)
            if signal_bus:
                enriched_signals = signal_bus.query(signal_type="intel_enriched_consensus")
                # Find latest enriched signal for this symbol
                for s in reversed(enriched_signals):
                    if s.payload.get("symbol") == symbol:
                        intel_enrichment = s.payload
                        break

            if intel_enrichment:
                if intel_enrichment.get("vetoed", False):
                    return []
```

Then replace the confidence calculation (~line 94):

```python
        # Derive signal
        signal = "BUY" if direction_score > 0 else "SELL"

        if intel_enrichment and "enriched_confidence" in intel_enrichment:
            confidence = intel_enrichment["enriched_confidence"]
        else:
            confidence = min(abs(direction_score) * view.agreement_ratio, 1.0)
```

And add intel_summary to the Opportunity `data` dict (~line 110):

```python
                    "is_low_confidence": view.is_low_confidence,
                    "intel": intel_enrichment.get("intel") if intel_enrichment else None,
```

- [ ] **Step 3: Run tests**

Run: `cd trading && python -m pytest tests/unit/test_intel_gate.py tests/unit/test_bittensor_source.py -v --tb=short`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add trading/strategies/bittensor_signal.py trading/tests/unit/test_intel_gate.py
git commit -m "feat(intel): add gate 9 (intel veto) + enriched confidence to BittensorSignalAgent"
```

---

### Task 11: API Status Endpoint

**Files:**
- Modify: `trading/api/routes/bittensor_schemas.py`
- Modify: `trading/api/routes/bittensor.py`

- [ ] **Step 1: Add schema**

In `trading/api/routes/bittensor_schemas.py`, add before `BittensorStatusResponse`:

```python
class IntelProviderStatus(BaseModel):
    circuit: str
    failures: int


class IntelligenceStatus(BaseModel):
    enabled: bool
    providers: dict[str, IntelProviderStatus]
    enrichments_applied: int
    vetos_issued: int
    provider_failures: int
    total_calls: int
```

Add `intelligence` field to `BittensorStatusResponse`:

```python
class BittensorStatusResponse(BaseModel):
    enabled: bool
    healthy: bool | None = None
    scheduler: SchedulerStatus | None = None
    miners: MinerSummary | None = None
    agent: AgentSummary | None = None
    bridge: BridgeStatus | None = None
    consensus_aggregator: dict[str, dict] | None = None
    intelligence: IntelligenceStatus | None = None
```

- [ ] **Step 2: Add to status endpoint**

In `trading/api/routes/bittensor.py`, in `bittensor_status()`, before the `return` statement (~line 112):

```python
    # Intelligence Layer section
    intel_layer = getattr(request.app.state, "intelligence_layer", None)
    intel_data = intel_layer.get_status() if intel_layer else None
```

Add `"intelligence": intel_data` to the return dict.

- [ ] **Step 3: Commit**

```bash
git add trading/api/routes/bittensor_schemas.py trading/api/routes/bittensor.py
git commit -m "feat(intel): add intelligence status to /api/bittensor/status endpoint"
```

---

### Task 12: Update agents.yaml

**Files:**
- Modify: `trading/agents.yaml`

- [ ] **Step 1: Add intel params to bittensor agents**

Update `bittensor_btc_5m` parameters (line ~111):

```yaml
  - name: bittensor_btc_5m
    strategy: bittensor_signal
    schedule: continuous
    interval: 60
    action_level: notify
    trust_level: monitored
    parameters:
      symbol: BTCUSD
      timeframe: 5m
      max_signal_age_seconds: 600
      min_responses_for_opportunity: 3
      min_agreement_ratio: 0.65
      min_abs_direction: 0.20
      min_expected_return: 0.002
      max_weighting_divergence: 0.25
      use_weighted_view: false
      allow_short_signals: true
      intel_enabled: true
      intel_weights:
        on_chain: 0.15
        sentiment: 0.10
        anomaly: 0.05
      intel_veto_threshold: 1
```

Update `bittensor_eth_5m` with the same intel params.

- [ ] **Step 2: Commit**

```bash
git add trading/agents.yaml
git commit -m "feat(intel): enable intel enrichment on bittensor BTC/ETH agents"
```

---

### Task 13: Run Full Test Suite

- [ ] **Step 1: Run all intel tests**

Run: `cd trading && python -m pytest tests/unit/test_intel_models.py tests/unit/test_intel_circuit_breaker.py tests/unit/test_intel_enrichment.py tests/unit/test_intel_providers.py tests/unit/test_intel_layer.py tests/unit/test_intel_gate.py -v --tb=short`
Expected: All pass (5 + 7 + 10 + 14 + 5 + 2 = 43 tests)

- [ ] **Step 2: Run existing test suite to check for regressions**

Run: `cd trading && python -m pytest tests/unit/ -v --tb=short --timeout=30`
Expected: All existing tests still pass

- [ ] **Step 3: Fix any regressions if found**

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git commit -m "fix(intel): resolve test regressions from intelligence layer integration"
```
