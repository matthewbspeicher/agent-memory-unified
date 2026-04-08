# Arena Alpha Sprint 2: The Game Begins

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ELO ratings live — track signals, match outcomes, update ratings hourly, feed tier weights into consensus router.

**Architecture:** `tracker.py` subscribes to SignalBus, `matcher.py` runs hourly batch, `calibration.py` tracks confidence accuracy. Consensus router reads tier from `elo_ratings`.

**Tech Stack:** Python 3.13, asyncpg, Pydantic, APScheduler

**Prereqs:** Sprint 1 complete (tables, models, engine, store, registry, API routes exist)

**Spec:** `docs/superpowers/specs/2026-04-07-arena-alpha-design.md` — Section 1 (Match Semantics, Calibration, Edge Cases) + Section 4 Sprint 2

---

### Task 1: Signal Tracker

**Files:**
- Create: `trading/competition/tracker.py`
- Create: `tests/unit/competition/test_tracker.py`

The tracker subscribes to `SignalBus` and records every signal with its competitor_id, asset, direction, confidence, and timestamp into a lightweight in-memory buffer. The matcher reads and drains this buffer hourly.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/competition/test_tracker.py
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from agents.models import AgentSignal
from competition.tracker import SignalTracker, TrackedSignal


class TestSignalTracker:
    @pytest.mark.asyncio
    async def test_track_signal_from_agent(self):
        tracker = SignalTracker()
        signal = AgentSignal(
            source_agent="rsi_scanner",
            signal_type="opportunity",
            payload={"symbol": "BTCUSD", "direction": "long", "confidence": 0.85},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        await tracker.on_signal(signal)
        assert len(tracker.pending_signals) == 1
        tracked = tracker.pending_signals[0]
        assert tracked.source_agent == "rsi_scanner"
        assert tracked.asset == "BTC"
        assert tracked.direction == "long"
        assert tracked.confidence == 0.85

    @pytest.mark.asyncio
    async def test_drain_returns_and_clears(self):
        tracker = SignalTracker()
        signal = AgentSignal(
            source_agent="rsi_scanner",
            signal_type="opportunity",
            payload={"symbol": "BTCUSD", "direction": "long", "confidence": 0.7},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        await tracker.on_signal(signal)
        drained = tracker.drain()
        assert len(drained) == 1
        assert len(tracker.pending_signals) == 0

    @pytest.mark.asyncio
    async def test_ignores_non_opportunity_signals(self):
        tracker = SignalTracker()
        signal = AgentSignal(
            source_agent="meta_agent",
            signal_type="meta_update",
            payload={},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        await tracker.on_signal(signal)
        assert len(tracker.pending_signals) == 0

    def test_normalize_symbol_strips_usd(self):
        tracker = SignalTracker()
        assert tracker._normalize_asset("BTCUSD") == "BTC"
        assert tracker._normalize_asset("ETHUSD") == "ETH"
        assert tracker._normalize_asset("BTC/USDT") == "BTC"
        assert tracker._normalize_asset("BTC") == "BTC"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/competition/test_tracker.py -v --tb=short --timeout=30`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# trading/competition/tracker.py
"""Subscribes to SignalBus and buffers signals for hourly match processing."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agents.models import AgentSignal

logger = logging.getLogger(__name__)

# Signal types that represent tradeable opportunities
TRACKABLE_SIGNAL_TYPES = {"opportunity", "bittensor_consensus", "intel_enriched_consensus"}


@dataclass
class TrackedSignal:
    source_agent: str
    asset: str
    direction: str  # "long" | "short" | "close"
    confidence: float
    timestamp: datetime
    payload: dict = field(default_factory=dict)


class SignalTracker:
    """Collects signals from SignalBus for competition match processing."""

    def __init__(self) -> None:
        self.pending_signals: list[TrackedSignal] = []

    async def on_signal(self, signal: AgentSignal) -> None:
        """SignalBus callback — filter and buffer relevant signals."""
        if signal.signal_type not in TRACKABLE_SIGNAL_TYPES:
            return

        payload = signal.payload or {}
        symbol = payload.get("symbol", "")
        direction = payload.get("direction") or payload.get("signal", "")
        confidence = signal.confidence or payload.get("confidence", 0.5)

        if not symbol or not direction:
            return

        asset = self._normalize_asset(symbol)
        tracked = TrackedSignal(
            source_agent=signal.source_agent,
            asset=asset,
            direction=str(direction),
            confidence=float(confidence),
            timestamp=signal.timestamp,
            payload=payload,
        )
        self.pending_signals.append(tracked)
        logger.debug("competition.tracker: buffered signal from %s on %s", signal.source_agent, asset)

    def drain(self) -> list[TrackedSignal]:
        """Return all pending signals and clear the buffer."""
        signals = self.pending_signals[:]
        self.pending_signals.clear()
        return signals

    def _normalize_asset(self, symbol: str) -> str:
        """BTCUSD -> BTC, BTC/USDT -> BTC, ETHUSD -> ETH."""
        cleaned = re.sub(r"[/\-]?(USD[T]?|USDT)$", "", symbol.upper())
        return cleaned
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && python -m pytest tests/unit/competition/test_tracker.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/competition/tracker.py tests/unit/competition/test_tracker.py
git commit -m "feat(competition): add SignalTracker for buffering signals"
```

---

### Task 2: Calibration Tracker

**Files:**
- Create: `trading/competition/calibration.py`
- Create: `tests/unit/competition/test_calibration.py`

Tracks rolling accuracy per confidence band. If a competitor claims high confidence but accuracy is low, their effective K-factor band is clamped down.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/competition/test_calibration.py
from __future__ import annotations

import pytest
from competition.calibration import CalibrationTracker


class TestCalibrationTracker:
    def test_initial_score_is_neutral(self):
        tracker = CalibrationTracker(window_size=10)
        score = tracker.get_calibration("agent_a", "high")
        assert score == 1.0  # No data = fully calibrated

    def test_perfect_calibration(self):
        tracker = CalibrationTracker(window_size=5)
        for _ in range(5):
            tracker.record("agent_a", "high", correct=True)
        assert tracker.get_calibration("agent_a", "high") == 1.0

    def test_poor_calibration(self):
        tracker = CalibrationTracker(window_size=5)
        for _ in range(5):
            tracker.record("agent_a", "high", correct=False)
        assert tracker.get_calibration("agent_a", "high") == 0.0

    def test_rolling_window(self):
        tracker = CalibrationTracker(window_size=3)
        tracker.record("agent_a", "high", correct=True)
        tracker.record("agent_a", "high", correct=True)
        tracker.record("agent_a", "high", correct=False)
        # 2/3 correct
        assert tracker.get_calibration("agent_a", "high") == pytest.approx(2 / 3, abs=0.01)
        # Add another correct — window slides
        tracker.record("agent_a", "high", correct=True)
        # Now: [True, False, True] = 2/3
        assert tracker.get_calibration("agent_a", "high") == pytest.approx(2 / 3, abs=0.01)

    def test_should_clamp_below_threshold(self):
        tracker = CalibrationTracker(window_size=10, clamp_threshold=0.65)
        for _ in range(10):
            tracker.record("agent_a", "high", correct=False)
        assert tracker.should_clamp("agent_a", "high") is True

    def test_no_clamp_above_threshold(self):
        tracker = CalibrationTracker(window_size=10, clamp_threshold=0.65)
        for _ in range(10):
            tracker.record("agent_a", "high", correct=True)
        assert tracker.should_clamp("agent_a", "high") is False

    def test_effective_confidence_band(self):
        tracker = CalibrationTracker(window_size=5, clamp_threshold=0.65)
        for _ in range(5):
            tracker.record("agent_a", "high", correct=False)
        # Should clamp "high" down to "medium"
        assert tracker.effective_band("agent_a", "high") == "medium"
        # Medium stays medium (not yet clamped further since no medium records)
        assert tracker.effective_band("agent_a", "medium") == "medium"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/competition/test_calibration.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# trading/competition/calibration.py
"""Confidence calibration tracking — clamps K-factor band if accuracy is poor."""
from __future__ import annotations

from collections import defaultdict, deque


BAND_ORDER = ["high", "medium", "low"]
BAND_DEMOTION = {"high": "medium", "medium": "low", "low": "low"}


class CalibrationTracker:
    """Rolling window accuracy tracker per competitor per confidence band."""

    def __init__(self, window_size: int = 100, clamp_threshold: float = 0.65):
        self._window_size = window_size
        self._clamp_threshold = clamp_threshold
        # {(competitor_ref, band): deque of bools}
        self._records: dict[tuple[str, str], deque[bool]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

    def record(self, competitor_ref: str, band: str, *, correct: bool) -> None:
        """Record a signal outcome for calibration tracking."""
        self._records[(competitor_ref, band)].append(correct)

    def get_calibration(self, competitor_ref: str, band: str) -> float:
        """Get accuracy score for a competitor at a confidence band. 0.0-1.0."""
        records = self._records.get((competitor_ref, band))
        if not records:
            return 1.0  # No data = assume calibrated
        return sum(records) / len(records)

    def should_clamp(self, competitor_ref: str, band: str) -> bool:
        """True if competitor's accuracy at this band is below threshold."""
        records = self._records.get((competitor_ref, band))
        if not records or len(records) < 5:
            return False  # Need minimum samples
        return self.get_calibration(competitor_ref, band) < self._clamp_threshold

    def effective_band(self, competitor_ref: str, claimed_band: str) -> str:
        """Return the effective confidence band after clamping."""
        if self.should_clamp(competitor_ref, claimed_band):
            return BAND_DEMOTION.get(claimed_band, claimed_band)
        return claimed_band
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && python -m pytest tests/unit/competition/test_calibration.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/competition/calibration.py tests/unit/competition/test_calibration.py
git commit -m "feat(competition): add CalibrationTracker for confidence clamping"
```

---

### Task 3: Match Processor (Hourly Batch)

**Files:**
- Create: `trading/competition/matcher.py`
- Create: `tests/unit/competition/test_matcher.py`

The matcher runs hourly: drains tracked signals, fetches prices, generates baseline + pairwise matches, updates ELO. This is the core game loop.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/competition/test_matcher.py
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from competition.matcher import MatchProcessor, MatchResult
from competition.tracker import TrackedSignal
from competition.engine import calculate_elo_delta


class MockCompetitionStore:
    def __init__(self):
        self._elos: dict[tuple[str, str], int] = {}
        self._updates: list[dict] = []
        self._competitors: dict[str, dict] = {}
        self._matches_recorded: list[dict] = []

    async def get_elo(self, competitor_id: str, asset: str) -> int:
        return self._elos.get((competitor_id, asset), 1000)

    async def update_elo(self, competitor_id: str, asset: str, new_elo: int, elo_delta: int) -> None:
        self._elos[(competitor_id, asset)] = new_elo
        self._updates.append({"id": competitor_id, "asset": asset, "elo": new_elo, "delta": elo_delta})

    async def get_competitor_by_ref(self, comp_type: str, ref_id: str) -> dict | None:
        return self._competitors.get(ref_id)

    async def record_match(self, match_data: dict) -> None:
        self._matches_recorded.append(match_data)

    def seed_competitor(self, ref_id: str, comp_id: str, elo: int = 1000) -> None:
        self._competitors[ref_id] = {"id": comp_id, "type": "agent", "ref_id": ref_id}
        self._elos[(comp_id, "BTC")] = elo


class MockPriceFetcher:
    def __init__(self, prices: dict[tuple[str, datetime], float] | None = None):
        self._prices = prices or {}
        self.default_price = 50000.0

    async def get_price(self, asset: str, at: datetime) -> float | None:
        return self._prices.get((asset, at), self.default_price)


class TestMatchProcessor:
    @pytest.mark.asyncio
    async def test_baseline_match_win(self):
        store = MockCompetitionStore()
        store.seed_competitor("rsi_scanner", "comp-1", elo=1000)
        fetcher = MockPriceFetcher()
        # Price went up — long was correct
        now = datetime.now(timezone.utc)
        fetcher._prices[(("BTC", now))] = 50000.0
        fetcher._prices[(("BTC", now + timedelta(minutes=5)))] = 50500.0

        processor = MatchProcessor(store=store, price_fetcher=fetcher)

        signal = TrackedSignal(
            source_agent="rsi_scanner",
            asset="BTC",
            direction="long",
            confidence=0.8,
            timestamp=now,
        )
        result = processor.evaluate_signal(signal, price_at_signal=50000.0, price_at_eval=50500.0)
        assert result.correct is True
        assert result.return_pct > 0

    @pytest.mark.asyncio
    async def test_baseline_match_loss(self):
        processor = MatchProcessor(store=MockCompetitionStore(), price_fetcher=MockPriceFetcher())
        signal = TrackedSignal(
            source_agent="rsi_scanner", asset="BTC", direction="long",
            confidence=0.7, timestamp=datetime.now(timezone.utc),
        )
        result = processor.evaluate_signal(signal, price_at_signal=50000.0, price_at_eval=49500.0)
        assert result.correct is False
        assert result.return_pct < 0

    @pytest.mark.asyncio
    async def test_short_signal_correct_on_drop(self):
        processor = MatchProcessor(store=MockCompetitionStore(), price_fetcher=MockPriceFetcher())
        signal = TrackedSignal(
            source_agent="rsi_scanner", asset="BTC", direction="short",
            confidence=0.6, timestamp=datetime.now(timezone.utc),
        )
        result = processor.evaluate_signal(signal, price_at_signal=50000.0, price_at_eval=49000.0)
        assert result.correct is True

    def test_pairwise_window_detection(self):
        processor = MatchProcessor(store=MockCompetitionStore(), price_fetcher=MockPriceFetcher())
        now = datetime.now(timezone.utc)
        signals = [
            TrackedSignal("agent_a", "BTC", "long", 0.8, now),
            TrackedSignal("agent_b", "BTC", "short", 0.7, now + timedelta(minutes=3)),
            TrackedSignal("agent_c", "ETH", "long", 0.9, now),  # different asset
            TrackedSignal("agent_d", "BTC", "long", 0.6, now + timedelta(minutes=10)),  # outside window
        ]
        pairs = processor.find_pairwise_matches(signals, window_minutes=5)
        # Only agent_a and agent_b are within 5min on same asset
        assert len(pairs) == 1
        assert {pairs[0][0].source_agent, pairs[0][1].source_agent} == {"agent_a", "agent_b"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && python -m pytest tests/unit/competition/test_matcher.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# trading/competition/matcher.py
"""Hourly batch match processor — evaluates signal outcomes, generates matches, updates ELO."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from competition.calibration import CalibrationTracker
from competition.engine import calculate_elo_delta, k_factor_for_confidence, k_factor_for_new_competitor
from competition.tracker import TrackedSignal

logger = logging.getLogger(__name__)

BASELINE_ELO = 1000
PAIRWISE_WINDOW_MINUTES = 5


class PriceFetcher(Protocol):
    async def get_price(self, asset: str, at: datetime) -> float | None: ...


@dataclass
class MatchResult:
    correct: bool
    return_pct: float
    direction: str


@dataclass
class ProcessingStats:
    signals_processed: int = 0
    baseline_matches: int = 0
    pairwise_matches: int = 0
    skipped_no_price: int = 0


class MatchProcessor:
    """Processes buffered signals into ELO matches."""

    def __init__(
        self,
        store: Any,
        price_fetcher: PriceFetcher,
        calibration: CalibrationTracker | None = None,
        eval_delay_minutes: int = 5,
    ):
        self._store = store
        self._price_fetcher = price_fetcher
        self._calibration = calibration or CalibrationTracker()
        self._eval_delay = eval_delay_minutes

    def evaluate_signal(
        self,
        signal: TrackedSignal,
        price_at_signal: float,
        price_at_eval: float,
    ) -> MatchResult:
        """Determine if a signal was correct based on price movement."""
        pct_change = (price_at_eval - price_at_signal) / price_at_signal

        if signal.direction == "long":
            correct = pct_change > 0
            return_pct = pct_change
        elif signal.direction == "short":
            correct = pct_change < 0
            return_pct = -pct_change  # Short profits on drops
        else:
            correct = False
            return_pct = 0.0

        return MatchResult(correct=correct, return_pct=return_pct, direction=signal.direction)

    def find_pairwise_matches(
        self,
        signals: list[TrackedSignal],
        window_minutes: int = PAIRWISE_WINDOW_MINUTES,
    ) -> list[tuple[TrackedSignal, TrackedSignal]]:
        """Find pairs of signals on the same asset within the time window."""
        pairs: list[tuple[TrackedSignal, TrackedSignal]] = []
        used: set[int] = set()

        for i, sig_a in enumerate(signals):
            if i in used:
                continue
            for j, sig_b in enumerate(signals[i + 1 :], start=i + 1):
                if j in used:
                    continue
                if sig_a.asset != sig_b.asset:
                    continue
                if sig_a.source_agent == sig_b.source_agent:
                    continue
                dt = abs((sig_a.timestamp - sig_b.timestamp).total_seconds())
                if dt <= window_minutes * 60:
                    pairs.append((sig_a, sig_b))
                    used.add(i)
                    used.add(j)
                    break  # Each signal pairs once

        return pairs

    async def process_batch(self, signals: list[TrackedSignal]) -> ProcessingStats:
        """Process a batch of signals: evaluate, match, update ELO."""
        stats = ProcessingStats(signals_processed=len(signals))
        now = datetime.now(timezone.utc)

        # Evaluate each signal
        evaluated: list[tuple[TrackedSignal, MatchResult]] = []
        for sig in signals:
            price_then = await self._price_fetcher.get_price(sig.asset, sig.timestamp)
            eval_time = sig.timestamp + timedelta(minutes=self._eval_delay)
            if eval_time > now:
                continue  # Not enough time elapsed
            price_now = await self._price_fetcher.get_price(sig.asset, eval_time)

            if price_then is None or price_now is None:
                stats.skipped_no_price += 1
                continue

            result = self.evaluate_signal(sig, price_then, price_now)
            evaluated.append((sig, result))

        # Baseline matches: each signal vs Hodler
        for sig, result in evaluated:
            await self._process_baseline_match(sig, result)
            stats.baseline_matches += 1

            # Record calibration
            band = self._confidence_band(sig.confidence)
            self._calibration.record(sig.source_agent, band, correct=result.correct)

        # Pairwise matches
        pairs = self.find_pairwise_matches([s for s, _ in evaluated])
        result_map = {id(s): r for s, r in evaluated}
        for sig_a, sig_b in pairs:
            r_a = result_map.get(id(sig_a))
            r_b = result_map.get(id(sig_b))
            if r_a and r_b:
                await self._process_pairwise_match(sig_a, r_a, sig_b, r_b)
                stats.pairwise_matches += 1

        logger.info(
            "competition.matcher: processed %d signals, %d baseline, %d pairwise, %d skipped",
            stats.signals_processed, stats.baseline_matches, stats.pairwise_matches, stats.skipped_no_price,
        )
        return stats

    async def _process_baseline_match(self, sig: TrackedSignal, result: MatchResult) -> None:
        """Evaluate signal against buy-and-hold baseline."""
        record = await self._store.get_competitor_by_ref("agent", sig.source_agent)
        if not record:
            record = await self._store.get_competitor_by_ref("miner", sig.source_agent)
        if not record:
            record = await self._store.get_competitor_by_ref("provider", sig.source_agent)
        if not record:
            return

        comp_id = str(record["id"])
        current_elo = await self._store.get_elo(comp_id, sig.asset)

        # Determine K-factor
        band = self._confidence_band(sig.confidence)
        effective_band = self._calibration.effective_band(sig.source_agent, band)
        confidence_k = k_factor_for_confidence(
            {"high": 0.9, "medium": 0.7, "low": 0.3}.get(effective_band, 0.5)
        )

        outcome = 1.0 if result.correct else 0.0
        delta = calculate_elo_delta(current_elo, BASELINE_ELO, outcome, k=confidence_k)
        new_elo = current_elo + delta

        await self._store.update_elo(comp_id, sig.asset, new_elo, delta)

    async def _process_pairwise_match(
        self,
        sig_a: TrackedSignal, result_a: MatchResult,
        sig_b: TrackedSignal, result_b: MatchResult,
    ) -> None:
        """Head-to-head match between two signals on same asset."""
        rec_a = await self._store.get_competitor_by_ref("agent", sig_a.source_agent)
        rec_b = await self._store.get_competitor_by_ref("agent", sig_b.source_agent)
        if not rec_a or not rec_b:
            return

        id_a, id_b = str(rec_a["id"]), str(rec_b["id"])
        elo_a = await self._store.get_elo(id_a, sig_a.asset)
        elo_b = await self._store.get_elo(id_b, sig_b.asset)

        # Determine winner by return
        if result_a.return_pct > result_b.return_pct:
            outcome_a, outcome_b = 1.0, 0.0
        elif result_b.return_pct > result_a.return_pct:
            outcome_a, outcome_b = 0.0, 1.0
        else:
            outcome_a, outcome_b = 0.5, 0.5  # Draw

        k = 20  # Standard K for pairwise
        delta_a = calculate_elo_delta(elo_a, elo_b, outcome_a, k=k)
        delta_b = calculate_elo_delta(elo_b, elo_a, outcome_b, k=k)

        await self._store.update_elo(id_a, sig_a.asset, elo_a + delta_a, delta_a)
        await self._store.update_elo(id_b, sig_b.asset, elo_b + delta_b, delta_b)

    @staticmethod
    def _confidence_band(confidence: float) -> str:
        if confidence >= 0.8:
            return "high"
        if confidence >= 0.5:
            return "medium"
        return "low"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd trading && python -m pytest tests/unit/competition/test_matcher.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/competition/matcher.py tests/unit/competition/test_matcher.py
git commit -m "feat(competition): add MatchProcessor for hourly ELO updates"
```

---

### Task 4: Wire Tracker + Matcher Into App Lifespan

**Files:**
- Modify: `trading/api/app.py`
- Modify: `trading/competition/store.py` (add `record_match` method)

- [ ] **Step 1: Add record_match to store**

In `trading/competition/store.py`, add this method to `CompetitionStore`:

```python
    async def record_match(self, match_data: dict) -> None:
        sql = """
            INSERT INTO matches (
                competitor_a_id, competitor_b_id, asset, window,
                winner_id, score_a, score_b, elo_delta_a, elo_delta_b, match_type
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """
        await self._db.execute(sql, [
            match_data.get("competitor_a_id"),
            match_data.get("competitor_b_id"),
            match_data.get("asset", "BTC"),
            match_data.get("window", "5m"),
            match_data.get("winner_id"),
            match_data.get("score_a", 0),
            match_data.get("score_b", 0),
            match_data.get("elo_delta_a", 0),
            match_data.get("elo_delta_b", 0),
            match_data.get("match_type", "baseline"),
        ])
```

- [ ] **Step 2: Wire into app lifespan**

In `trading/api/app.py`, expand the competition section added in Sprint 1. After registry registration, add:

```python
    # Competition tracker + matcher
    from competition.tracker import SignalTracker
    from competition.matcher import MatchProcessor
    from competition.calibration import CalibrationTracker

    if config.competition.enabled:
        competition_tracker = SignalTracker()
        competition_calibration = CalibrationTracker()
        signal_bus.subscribe(competition_tracker.on_signal)

        # Simple price fetcher using DataBus
        class _PriceFetcher:
            def __init__(self, data_bus):
                self._data_bus = data_bus
            async def get_price(self, asset, at):
                try:
                    quote = await self._data_bus.quote(f"{asset}USD")
                    return quote.get("last") or quote.get("price")
                except Exception:
                    return None

        competition_matcher = MatchProcessor(
            store=competition_store,
            price_fetcher=_PriceFetcher(data_bus),
            calibration=competition_calibration,
        )
        app.state.competition_tracker = competition_tracker
        app.state.competition_matcher = competition_matcher

        # Hourly match processing task
        async def _competition_match_loop():
            import asyncio
            while True:
                await asyncio.sleep(3600)  # 1 hour
                try:
                    signals = competition_tracker.drain()
                    if signals:
                        await competition_matcher.process_batch(signals)
                except Exception as exc:
                    logger.error("competition.match_loop failed: %s", exc)

        task_mgr.create_task(_competition_match_loop(), name="competition_matcher")
```

- [ ] **Step 3: Commit**

```bash
git add trading/api/app.py trading/competition/store.py
git commit -m "feat(competition): wire tracker and matcher into app lifespan"
```

---

### Task 5: Tier-Based Consensus Weight Integration

**Files:**
- Modify: `trading/agents/consensus.py`

- [ ] **Step 1: Read current consensus.py**

Read `trading/agents/consensus.py` and locate the `compute_vote_weight` method and `AgentWeightProfile` class. The profile already has `elo_rating: int = 1000`.

- [ ] **Step 2: Add tier weight multiplier**

In `EnhancedConsensusRouter`, find `compute_vote_weight()`. Add a tier-based multiplier when `WeightSource.ELO` or `WeightSource.COMPOSITE` is active:

```python
    def _tier_weight_multiplier(self, elo: int) -> float:
        """Competition tier affects vote weight."""
        if elo >= 1400:
            return 1.5   # Diamond
        if elo >= 1200:
            return 1.0   # Gold
        if elo >= 1000:
            return 0.8   # Silver
        return 0.0        # Bronze = shadow mode (no weight)
```

Call this in `compute_vote_weight` when `self._config.weight_source in (WeightSource.ELO, WeightSource.COMPOSITE)`. Multiply the existing weight by `self._tier_weight_multiplier(profile.elo_rating)`.

- [ ] **Step 3: Verify existing tests still pass**

Run: `cd trading && python -m pytest tests/unit/ -v --tb=short --timeout=30 -k consensus`
Expected: All PASS (existing consensus tests should still work since tier multiplier only activates with ELO weight source)

- [ ] **Step 4: Commit**

```bash
git add trading/agents/consensus.py
git commit -m "feat(competition): add tier weight multiplier to consensus router"
```

---

### Task 6: Frontend — Live ELO, Filters, Baseline Row

**Files:**
- Modify: `frontend/src/pages/Arena.tsx`
- Modify: `frontend/src/components/competition/LeaderboardTable.tsx`

- [ ] **Step 1: Add baseline row to LeaderboardTable**

In `LeaderboardTable.tsx`, after the main `<tbody>`, add a baseline row:

```tsx
{/* Baseline row — pinned at bottom */}
<tfoot>
  <tr className="border-t-2 border-gray-600 bg-gray-900/50">
    <td className="py-2 px-2 text-gray-600">—</td>
    <td className="py-2 px-2"><span className="text-gray-600 text-xs">BASE</span></td>
    <td className="py-2 px-2 text-gray-500 italic">Hodler (baseline)</td>
    <td className="py-2 px-2 text-gray-600 text-xs">baseline</td>
    <td className="py-2 px-2 text-right font-mono text-gray-500">1000</td>
    <td className="py-2 px-2 text-right text-gray-600">—</td>
    <td className="py-2 px-2 text-right text-gray-600">—</td>
  </tr>
</tfoot>
```

- [ ] **Step 2: Add visibility-based polling to Arena.tsx**

The existing `useLeaderboard` hook already has 30s refetch. Wrap it to slow down when tab is inactive:

```tsx
// In Arena.tsx, update the useLeaderboard call:
const { data, isLoading } = useQuery({
  queryKey: ['competition', 'leaderboard', asset, typeFilter],
  queryFn: () => competitionApi.getLeaderboard({ asset, type: typeFilter }),
  refetchInterval: isTabActive ? 30_000 : 120_000,
});
```

Replace the `useLeaderboard` import with direct `useQuery` + `competitionApi` import.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Arena.tsx frontend/src/components/competition/LeaderboardTable.tsx
git commit -m "feat(frontend): add baseline row and visibility-based polling"
```

---

### Task 7: Sprint 2 Integration Test

- [ ] **Step 1: Run all competition unit tests**

Run: `cd trading && python -m pytest tests/unit/competition/ -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 2: Verify no regressions in existing tests**

Run: `cd trading && python -m pytest tests/unit/ -v --tb=short --timeout=30 --ignore=tests/unit/competition`
Expected: No new failures

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(competition): complete Sprint 2 — live ELO, matcher, calibration"
```
