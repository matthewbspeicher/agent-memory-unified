# Arena Alpha Sprint 3: CCXT + Funding Rate Data

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the CCXT exchange client stub into a full async data source with funding rates, OI, and partial failure handling. Wire into intelligence layer.

**Architecture:** Expand existing `trading/data/exchange_client.py` (51 lines) into a full CCXT wrapper. New `trading/data/sources/derivatives.py` for funding rate + OI data. Wire both into `AnomalyProvider` and intelligence layer.

**Tech Stack:** Python 3.13, ccxt (async_support), Redis caching

**Prereqs:** Sprint 1-2 complete

**Spec:** `docs/superpowers/specs/2026-04-07-arena-alpha-design.md` — Section 2.1 + 2.2

---

### Task 1: Expand ExchangeClient

**Files:**
- Modify: `trading/data/exchange_client.py`
- Create: `tests/unit/data/test_exchange_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/data/test_exchange_client.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from data.exchange_client import ExchangeClient, FetchResult, FetchError


class TestFetchResult:
    def test_is_complete_all_present(self):
        result = FetchResult(
            ohlcv=[{"close": 50000}],
            funding={"rate": 0.001},
            oi=1_000_000.0,
            orderbook={"bids": [], "asks": []},
        )
        assert result.is_complete is True

    def test_is_complete_partial(self):
        result = FetchResult(ohlcv=[{"close": 50000}])
        assert result.is_complete is False
        assert result.partial_success is True

    def test_empty_result(self):
        result = FetchResult()
        assert result.is_complete is False
        assert result.partial_success is False

    def test_available_data_types(self):
        result = FetchResult(ohlcv=[{"close": 50000}], funding={"rate": 0.001})
        assert set(result.available_data_types) == {"ohlcv", "funding"}

    def test_errors_tracked(self):
        result = FetchResult(
            errors=[FetchError(exchange="binance", data_type="oi", error="timeout")]
        )
        assert len(result.errors) == 1
        assert result.errors[0].exchange == "binance"


class TestExchangeClientNormalize:
    def test_btcusd_to_spot(self):
        client = ExchangeClient.__new__(ExchangeClient)
        assert client._format_spot("BTCUSD") == "BTC/USDT"
        assert client._format_spot("ETHUSD") == "ETH/USDT"

    def test_btcusd_to_perp(self):
        client = ExchangeClient.__new__(ExchangeClient)
        assert client._format_perp("BTCUSD") == "BTC/USDT:USDT"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd trading && python -m pytest tests/unit/data/test_exchange_client.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 3: Rewrite exchange_client.py**

Read the existing `trading/data/exchange_client.py` first, then replace with:

```python
# trading/data/exchange_client.py
"""Unified CCXT exchange client with fallback and partial failure handling."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import ccxt.async_support as ccxt

from intelligence.circuit_breaker import ProviderCircuitBreaker

logger = logging.getLogger(__name__)


@dataclass
class FetchError:
    exchange: str
    data_type: str
    error: str


@dataclass
class FetchResult:
    ohlcv: list[dict] | None = None
    funding: dict | None = None
    oi: float | None = None
    orderbook: dict | None = None
    errors: list[FetchError] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_complete(self) -> bool:
        return all(v is not None for v in [self.ohlcv, self.funding, self.oi, self.orderbook])

    @property
    def partial_success(self) -> bool:
        return any(v is not None for v in [self.ohlcv, self.funding, self.oi, self.orderbook])

    @property
    def available_data_types(self) -> list[str]:
        types = []
        if self.ohlcv is not None: types.append("ohlcv")
        if self.funding is not None: types.append("funding")
        if self.oi is not None: types.append("oi")
        if self.orderbook is not None: types.append("orderbook")
        return types


class ExchangeClient:
    """Async CCXT wrapper with multi-exchange fallback and circuit breakers."""

    def __init__(
        self,
        primary: str = "binance",
        fallbacks: list[str] | None = None,
        enable_rate_limit: bool = True,
    ):
        self._exchange_ids = [primary] + (fallbacks or [])
        self._exchanges: dict[str, ccxt.Exchange] = {}
        self._breakers: dict[str, ProviderCircuitBreaker] = {}

        for eid in self._exchange_ids:
            exchange_class = getattr(ccxt, eid, None)
            if exchange_class:
                self._exchanges[eid] = exchange_class({"enableRateLimit": enable_rate_limit})
                self._breakers[eid] = ProviderCircuitBreaker(failure_threshold=5, reset_timeout=60)

    def _format_spot(self, symbol: str) -> str:
        return symbol.replace("USD", "/USDT")

    def _format_perp(self, symbol: str) -> str:
        return symbol.replace("USD", "/USDT:USDT")

    async def fetch_all(self, symbol: str) -> FetchResult:
        """Fetch all data types with exchange fallback."""
        result = FetchResult()
        for eid in self._exchange_ids:
            exchange = self._exchanges.get(eid)
            breaker = self._breakers.get(eid)
            if not exchange or not breaker:
                continue
            if breaker.state == "open" and not breaker._should_attempt_reset():
                continue

            try:
                if result.ohlcv is None:
                    result.ohlcv = await self._fetch_ohlcv(exchange, symbol)
            except Exception as e:
                result.errors.append(FetchError(eid, "ohlcv", str(e)))

            try:
                if result.funding is None:
                    result.funding = await self._fetch_funding(exchange, symbol)
            except Exception as e:
                result.errors.append(FetchError(eid, "funding", str(e)))

            try:
                if result.oi is None:
                    result.oi = await self._fetch_oi(exchange, symbol)
            except Exception as e:
                result.errors.append(FetchError(eid, "oi", str(e)))

            try:
                if result.orderbook is None:
                    result.orderbook = await self._fetch_orderbook(exchange, symbol)
            except Exception as e:
                result.errors.append(FetchError(eid, "orderbook", str(e)))

            if result.is_complete:
                break

        return result

    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Backward-compat: fetch ticker from primary exchange."""
        exchange = next(iter(self._exchanges.values()), None)
        if not exchange:
            return {}
        try:
            return await exchange.fetch_ticker(self._format_spot(symbol))
        except Exception as e:
            logger.warning("fetch_ticker failed: %s", e)
            return {}

    async def fetch_funding_rate(self, symbol: str) -> float:
        """Backward-compat: fetch funding rate from primary exchange."""
        exchange = next(iter(self._exchanges.values()), None)
        if not exchange:
            return 0.0
        try:
            data = await exchange.fetch_funding_rate(self._format_perp(symbol))
            return data.get("fundingRate", 0.0)
        except Exception as e:
            logger.warning("fetch_funding_rate failed: %s", e)
            return 0.0

    async def _fetch_ohlcv(self, exchange: ccxt.Exchange, symbol: str) -> list[dict]:
        raw = await exchange.fetch_ohlcv(self._format_spot(symbol), "1m", limit=100)
        return [
            {"timestamp": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
            for r in raw
        ]

    async def _fetch_funding(self, exchange: ccxt.Exchange, symbol: str) -> dict:
        data = await exchange.fetch_funding_rate(self._format_perp(symbol))
        rate = data.get("fundingRate", 0.0)
        return {
            "rate": rate,
            "annualized": rate * 3 * 365,
            "timestamp": data.get("timestamp"),
        }

    async def _fetch_oi(self, exchange: ccxt.Exchange, symbol: str) -> float:
        try:
            data = await exchange.fetch_open_interest(self._format_perp(symbol))
            return float(data.get("openInterestAmount", 0) or 0)
        except (ccxt.NotSupported, AttributeError):
            return 0.0

    async def _fetch_orderbook(self, exchange: ccxt.Exchange, symbol: str) -> dict:
        book = await exchange.fetch_order_book(self._format_spot(symbol), limit=20)
        return {"bids": book.get("bids", [])[:20], "asks": book.get("asks", [])[:20]}

    async def close(self) -> None:
        for exchange in self._exchanges.values():
            await exchange.close()
```

- [ ] **Step 4: Run tests**

Run: `cd trading && python -m pytest tests/unit/data/test_exchange_client.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/data/exchange_client.py tests/unit/data/test_exchange_client.py
git commit -m "feat(exchange): expand ExchangeClient with FetchResult and fallback"
```

---

### Task 2: Derivatives Data Source

**Files:**
- Create: `trading/data/sources/derivatives.py`
- Create: `tests/unit/data/test_derivatives.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/data/test_derivatives.py
from __future__ import annotations

import math
import pytest
from data.sources.derivatives import FundingOISnapshot, DerivativesDataSource
from data.exchange_client import FetchResult


class TestFundingOISnapshot:
    def test_crowdedness_score(self):
        snap = FundingOISnapshot(
            symbol="BTCUSD",
            exchange="binance",
            funding_rate=0.001,
            annualized_rate=0.001 * 3 * 365,
            open_interest=1_000_000_000,
            oi_change_24h=0.05,
        )
        expected = snap.annualized_rate * math.log(snap.open_interest)
        assert snap.crowdedness_score == pytest.approx(expected, abs=0.01)

    def test_zero_oi_crowdedness(self):
        snap = FundingOISnapshot(
            symbol="BTCUSD", exchange="binance",
            funding_rate=0.001, annualized_rate=1.095,
            open_interest=0, oi_change_24h=0,
        )
        assert snap.crowdedness_score == 0.0


class TestDerivativesDataSource:
    @pytest.mark.asyncio
    async def test_from_fetch_result(self):
        result = FetchResult(
            funding={"rate": 0.0005, "annualized": 0.0005 * 3 * 365},
            oi=500_000_000.0,
        )
        source = DerivativesDataSource()
        snap = source.snapshot_from_fetch("BTCUSD", "binance", result)
        assert snap is not None
        assert snap.funding_rate == 0.0005
        assert snap.annualized_rate == pytest.approx(0.0005 * 3 * 365)
        assert snap.open_interest == 500_000_000.0

    @pytest.mark.asyncio
    async def test_from_fetch_result_missing_funding(self):
        result = FetchResult(oi=500_000_000.0)
        source = DerivativesDataSource()
        snap = source.snapshot_from_fetch("BTCUSD", "binance", result)
        assert snap is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd trading && python -m pytest tests/unit/data/test_derivatives.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# trading/data/sources/derivatives.py
"""Funding rate + open interest data source."""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FundingOISnapshot:
    symbol: str
    exchange: str
    funding_rate: float
    annualized_rate: float
    open_interest: float
    oi_change_24h: float

    @property
    def crowdedness_score(self) -> float:
        if self.open_interest <= 0:
            return 0.0
        return self.annualized_rate * math.log(self.open_interest)


class DerivativesDataSource:
    """Processes exchange data into funding rate snapshots."""

    def snapshot_from_fetch(
        self,
        symbol: str,
        exchange: str,
        fetch_result: Any,
    ) -> FundingOISnapshot | None:
        funding = fetch_result.funding
        if funding is None:
            return None

        rate = funding.get("rate", 0.0)
        annualized = funding.get("annualized", rate * 3 * 365)
        oi = fetch_result.oi or 0.0

        return FundingOISnapshot(
            symbol=symbol,
            exchange=exchange,
            funding_rate=rate,
            annualized_rate=annualized,
            open_interest=oi,
            oi_change_24h=0.0,  # Requires historical tracking
        )
```

- [ ] **Step 4: Run tests**

Run: `cd trading && python -m pytest tests/unit/data/test_derivatives.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/data/sources/derivatives.py tests/unit/data/test_derivatives.py
git commit -m "feat(data): add DerivativesDataSource with FundingOISnapshot"
```

---

### Task 3: Wire Into Intelligence Layer

**Files:**
- Modify: `trading/intelligence/layer.py`

- [ ] **Step 1: Read current intelligence/layer.py**

Read `trading/intelligence/layer.py` and locate where providers are registered in `__init__`.

- [ ] **Step 2: Add derivatives provider reference**

The intelligence layer already has a `_derivatives` provider slot. Verify it's initialized and connected to the new ExchangeClient. If it's stubbed or None, wire it to use `ExchangeClient.fetch_all()` + `DerivativesDataSource.snapshot_from_fetch()`.

This is a light wiring task — the provider interface (`BaseIntelProvider.analyze()`) returns `IntelReport`. The derivatives provider should fetch funding data and return a report with `score` based on funding rate direction.

- [ ] **Step 3: Verify no regressions**

Run: `cd trading && python -m pytest tests/unit/ -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add trading/intelligence/layer.py
git commit -m "feat(intel): wire derivatives provider to expanded ExchangeClient"
```

- [ ] **Step 5: Final Sprint 3 commit**

```bash
git add -A
git commit -m "feat: complete Sprint 3 — CCXT exchange client and derivatives data"
```
