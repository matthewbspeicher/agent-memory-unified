"""Unit tests for SignalFeatureCapture and indicator helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from broker.models import AssetType, Bar, Quote, Symbol
from data.indicators import (
    compute_atr,
    compute_realized_vol,
    compute_relative_volume,
)
from storage.db import init_db
from storage.signal_features import SignalFeatureStore


# ---------------------------------------------------------------------------
# Indicator helper tests
# ---------------------------------------------------------------------------

_SYM = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)


def _make_bars(n: int, base_close: float = 100.0, vol: int = 1_000_000) -> list[Bar]:
    """Generate n synthetic daily bars with slight price drift."""
    bars = []
    price = base_close
    for i in range(n):
        price = price * (1 + 0.002 * (1 if i % 2 == 0 else -1))
        bars.append(
            Bar(
                symbol=_SYM,
                open=Decimal(str(round(price * 0.99, 4))),
                high=Decimal(str(round(price * 1.01, 4))),
                low=Decimal(str(round(price * 0.98, 4))),
                close=Decimal(str(round(price, 4))),
                volume=vol + i * 1000,
            )
        )
    return bars


class TestComputeAtr:
    def test_normal_case(self):
        bars = _make_bars(30)
        atr = compute_atr(bars, period=14)
        assert atr > 0

    def test_insufficient_bars_raises(self):
        bars = _make_bars(5)
        with pytest.raises(ValueError, match="bars for ATR"):
            compute_atr(bars, period=14)

    def test_exactly_minimum_bars(self):
        bars = _make_bars(15)  # period+1 = 15
        atr = compute_atr(bars, period=14)
        assert atr > 0


class TestComputeRealizedVol:
    def test_normal_case(self):
        bars = _make_bars(30)
        vol = compute_realized_vol(bars, period=20)
        assert vol > 0

    def test_annualized(self):
        """Result should be annualized (roughly in 0–5 range for normal stocks)."""
        bars = _make_bars(30)
        vol = compute_realized_vol(bars, period=20)
        assert 0 < vol < 5.0

    def test_insufficient_bars_raises(self):
        bars = _make_bars(10)
        with pytest.raises(ValueError, match="realized vol"):
            compute_realized_vol(bars, period=20)


class TestComputeRelativeVolume:
    def test_normal_case(self):
        bars = _make_bars(25, vol=1_000_000)
        rel_vol = compute_relative_volume(bars, period=20)
        assert rel_vol > 0

    def test_volume_spike(self):
        """A high-volume last bar should yield rel vol > 1."""
        bars = _make_bars(25, vol=1_000_000)
        # Replace last bar with a spike
        last = bars[-1]
        bars[-1] = Bar(
            symbol=_SYM,
            open=last.open,
            high=last.high,
            low=last.low,
            close=last.close,
            volume=5_000_000,
        )
        rel_vol = compute_relative_volume(bars, period=20)
        assert rel_vol > 1.0

    def test_insufficient_bars_raises(self):
        bars = _make_bars(5)
        with pytest.raises(ValueError, match="relative volume"):
            compute_relative_volume(bars, period=20)

    def test_zero_avg_volume_returns_one(self):
        # Build bars with all-zero volumes explicitly
        price = Decimal("100")
        zero_bars = [
            Bar(symbol=_SYM, open=price, high=price, low=price, close=price, volume=0)
            for _ in range(20)
        ]
        rel_vol = compute_relative_volume(zero_bars, period=20)
        assert rel_vol == 1.0


# ---------------------------------------------------------------------------
# SignalFeatureCapture tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def sf_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield SignalFeatureStore(db)
    await db.close()


def _make_opportunity(
    opp_id: str = "opp-test",
    ticker: str = "AAPL",
    asset_type: AssetType = AssetType.STOCK,
    confidence: float = 0.8,
    data: dict | None = None,
) -> MagicMock:
    opp = MagicMock()
    opp.id = opp_id
    opp.agent_name = "test_agent"
    opp.symbol = Symbol(ticker=ticker, asset_type=asset_type)
    opp.signal = "test_signal"
    opp.confidence = confidence
    opp.broker_id = None
    opp.timestamp = datetime.now(timezone.utc)
    opp.data = data or {}
    return opp


def _make_data_bus(
    bars: list[Bar] | None = None, quote: Quote | None = None
) -> MagicMock:
    bus = MagicMock()
    bus.get_quote = AsyncMock(return_value=quote)
    bus.get_historical = AsyncMock(return_value=bars or [])
    return bus


class TestSignalFeatureCapture:
    async def test_full_capture_with_bars(self, sf_store: SignalFeatureStore):
        from learning.signal_features import SignalFeatureCapture
        from agents.models import ActionLevel

        bars = _make_bars(70)
        quote = Quote(
            symbol=Symbol(ticker="AAPL"),
            bid=Decimal("149.90"),
            ask=Decimal("150.10"),
            last=Decimal("150.00"),
        )
        bus = _make_data_bus(bars=bars, quote=quote)
        capture = SignalFeatureCapture(store=sf_store, data_bus=bus)
        opp = _make_opportunity()

        await capture.capture(opp, ActionLevel.NOTIFY)

        row = await sf_store.get("opp-test")
        assert row is not None
        assert row["capture_status"] == "captured"
        assert row["rsi_14"] is not None
        assert row["sma_20"] is not None
        assert row["ema_20"] is not None
        assert row["macd_histogram"] is not None
        assert row["bollinger_pct_b"] is not None
        assert row["atr_14"] is not None
        assert row["realized_vol_20d"] is not None
        assert row["relative_volume_20d"] is not None
        assert row["quote_bid"] is not None
        assert row["spread_bps"] is not None
        assert row["feature_payload"]["action_level"] == "notify"

    async def test_partial_capture_no_bars(self, sf_store: SignalFeatureStore):
        from learning.signal_features import SignalFeatureCapture

        quote = Quote(
            symbol=Symbol(ticker="AAPL"),
            bid=Decimal("149.90"),
            ask=Decimal("150.10"),
            last=Decimal("150.00"),
        )
        bus = _make_data_bus(bars=[], quote=quote)
        capture = SignalFeatureCapture(store=sf_store, data_bus=bus)
        opp = _make_opportunity()

        await capture.capture(opp)

        row = await sf_store.get("opp-test")
        assert row is not None
        # Quote should be present
        assert row["quote_bid"] is not None
        # Indicators should be absent
        assert row["rsi_14"] is None
        assert row["sma_20"] is None

    async def test_failed_capture_stores_row(self, sf_store: SignalFeatureStore):
        """DataBus errors are caught per-call; the row is stored as 'partial'."""
        from learning.signal_features import SignalFeatureCapture

        bus = MagicMock()
        bus.get_quote = AsyncMock(side_effect=RuntimeError("network error"))
        bus.get_historical = AsyncMock(side_effect=RuntimeError("network error"))
        capture = SignalFeatureCapture(store=sf_store, data_bus=bus)
        opp = _make_opportunity()

        # Should not raise
        await capture.capture(opp)

        row = await sf_store.get("opp-test")
        assert row is not None
        # Per-call DataBus errors yield partial, not failed
        assert row["capture_status"] == "partial"
        assert row["agent_name"] == "test_agent"

    async def test_store_failure_produces_failed_row(
        self, sf_store: SignalFeatureStore
    ):
        """If the store itself fails during _do_capture, a failed row is written."""
        from learning.signal_features import SignalFeatureCapture

        bus = _make_data_bus(bars=[], quote=None)
        capture = SignalFeatureCapture(store=sf_store, data_bus=bus)
        opp = _make_opportunity()

        # Patch upsert to fail once then succeed (simulate transient error in _do_capture)
        call_count = 0
        original_upsert = sf_store.upsert

        async def _failing_upsert(opp_id, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("db down")
            return await original_upsert(opp_id, **kwargs)

        capture._store.upsert = _failing_upsert  # type: ignore[method-assign]
        await capture.capture(opp)

        row = await sf_store.get("opp-test")
        assert row is not None
        assert row["capture_status"] == "failed"

    async def test_agent_extras_merged_into_payload(self, sf_store: SignalFeatureStore):
        from learning.signal_features import SignalFeatureCapture

        bus = _make_data_bus(bars=[], quote=None)
        capture = SignalFeatureCapture(store=sf_store, data_bus=bus)
        opp = _make_opportunity(
            data={"signal_features": {"custom_score": 0.99, "algo_version": "v2"}}
        )

        await capture.capture(opp)

        row = await sf_store.get("opp-test")
        assert row is not None
        payload = row["feature_payload"]
        assert payload.get("custom_score") == pytest.approx(0.99)
        assert payload.get("algo_version") == "v2"

    async def test_regime_stamped_from_opportunity_data(
        self, sf_store: SignalFeatureStore
    ):
        from learning.signal_features import SignalFeatureCapture

        bus = _make_data_bus(bars=[], quote=None)
        capture = SignalFeatureCapture(store=sf_store, data_bus=bus)
        opp = _make_opportunity(
            data={
                "regime": {
                    "trend_regime": "uptrend",
                    "volatility_regime": "low",
                    "liquidity_regime": "high",
                }
            }
        )

        await capture.capture(opp)

        row = await sf_store.get("opp-test")
        assert row["trend_regime"] == "uptrend"
        assert row["volatility_regime"] == "low"
        assert row["liquidity_regime"] == "high"

    async def test_no_data_bus_stores_minimal_row(self, sf_store: SignalFeatureStore):
        from learning.signal_features import SignalFeatureCapture

        capture = SignalFeatureCapture(store=sf_store, data_bus=None)
        opp = _make_opportunity()

        await capture.capture(opp)

        row = await sf_store.get("opp-test")
        assert row is not None
        assert row["agent_name"] == "test_agent"
        assert row["symbol"] == "AAPL"
        assert row["rsi_14"] is None

    async def test_spread_bps_computed_correctly(self, sf_store: SignalFeatureStore):
        from learning.signal_features import SignalFeatureCapture

        # bid=99, ask=101 → spread=2, mid=100 → spread_bps = 2/100 * 10000 = 200
        quote = Quote(
            symbol=Symbol(ticker="AAPL"),
            bid=Decimal("99"),
            ask=Decimal("101"),
            last=Decimal("100"),
        )
        bus = _make_data_bus(bars=[], quote=quote)
        capture = SignalFeatureCapture(store=sf_store, data_bus=bus)
        opp = _make_opportunity()

        await capture.capture(opp)

        row = await sf_store.get("opp-test")
        assert row["spread_bps"] == pytest.approx(200.0, rel=0.01)

    async def test_distance_to_sma_ema(self, sf_store: SignalFeatureStore):
        from learning.signal_features import SignalFeatureCapture

        # Price trending above averages
        bars = _make_bars(60, base_close=200.0)
        bus = _make_data_bus(bars=bars, quote=None)
        capture = SignalFeatureCapture(store=sf_store, data_bus=bus)
        opp = _make_opportunity()

        await capture.capture(opp)

        row = await sf_store.get("opp-test")
        assert row["distance_to_sma20_pct"] is not None
        assert row["distance_to_ema20_pct"] is not None

    async def test_capture_delay_ms_recorded(self, sf_store: SignalFeatureStore):
        from learning.signal_features import SignalFeatureCapture

        bus = _make_data_bus(bars=[], quote=None)
        capture = SignalFeatureCapture(store=sf_store, data_bus=bus)
        opp = _make_opportunity()

        await capture.capture(opp)

        row = await sf_store.get("opp-test")
        assert row["capture_delay_ms"] is not None
        assert row["capture_delay_ms"] >= 0
