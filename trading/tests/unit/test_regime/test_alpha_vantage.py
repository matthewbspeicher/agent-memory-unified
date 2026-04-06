"""Tests for Alpha Vantage economic indicator enrichment in RegimeDetector (Task 4)."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from regime.detector import RegimeDetector
from regime.models import MarketRegime, RegimeSnapshot


def _make_bar(close: float):
    from broker.models import Bar, Symbol, AssetType

    return Bar(
        symbol=Symbol(ticker="SPY", asset_type=AssetType.STOCK),
        timestamp=datetime.now(timezone.utc),
        open=Decimal(str(close)),
        high=Decimal(str(close * 1.01)),
        low=Decimal(str(close * 0.99)),
        close=Decimal(str(close)),
        volume=1_000_000,
    )


def _trending_bars(n: int = 60) -> list:
    return [_make_bar(400.0 + i * 2.0) for i in range(n)]


# ---------------------------------------------------------------------------
# __init__ accepts alpha_vantage_key
# ---------------------------------------------------------------------------


def test_init_accepts_alpha_vantage_key():
    detector = RegimeDetector(alpha_vantage_key="AV-KEY")
    assert detector._alpha_vantage_key == "AV-KEY"


def test_init_default_key_is_none():
    detector = RegimeDetector()
    assert detector._alpha_vantage_key is None


# ---------------------------------------------------------------------------
# detect_with_snapshot_enriched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enriched_snapshot_contains_economic_data():
    """When AV key is set, detect_with_snapshot_enriched populates economic_data."""
    detector = RegimeDetector(alpha_vantage_key="AV-KEY")

    fake_econ = {
        "gdp": {"date": "2025-10-01", "value": "23500.0"},
        "fed_rate": {"date": "2025-12-01", "value": "5.33"},
    }
    with patch.object(
        detector, "_fetch_economic_indicators", new=AsyncMock(return_value=fake_econ)
    ):
        snapshot = await detector.detect_with_snapshot_enriched(_trending_bars())

    assert snapshot.economic_data == fake_econ
    assert isinstance(snapshot.regime, MarketRegime)


@pytest.mark.asyncio
async def test_enriched_snapshot_skips_fetch_when_no_key():
    """Without AV key, _fetch_economic_indicators is never called."""
    detector = RegimeDetector()  # no key

    with patch.object(
        detector, "_fetch_economic_indicators", new=AsyncMock()
    ) as mock_fetch:
        snapshot = await detector.detect_with_snapshot_enriched(_trending_bars())

    mock_fetch.assert_not_awaited()
    assert snapshot.economic_data is None


@pytest.mark.asyncio
async def test_enriched_snapshot_handles_fetch_failure_gracefully():
    """If _fetch_economic_indicators raises, the snapshot is still returned."""
    detector = RegimeDetector(alpha_vantage_key="AV-KEY")

    with patch.object(
        detector,
        "_fetch_economic_indicators",
        new=AsyncMock(return_value={"gdp": None, "fed_rate": None}),
    ):
        snapshot = await detector.detect_with_snapshot_enriched(_trending_bars())

    assert snapshot.economic_data == {"gdp": None, "fed_rate": None}
    assert snapshot.regime is not None


# ---------------------------------------------------------------------------
# _fetch_economic_indicators
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_economic_indicators_returns_latest_entries():
    detector = RegimeDetector(alpha_vantage_key="AV-KEY")

    gdp_json = {
        "data": [
            {"date": "2025-10-01", "value": "23500.0"},
            {"date": "2025-07-01", "value": "23100.0"},
        ]
    }
    rate_json = {
        "data": [
            {"date": "2025-12-01", "value": "5.33"},
            {"date": "2025-11-01", "value": "5.33"},
        ]
    }

    call_count = 0

    mock_response_gdp = MagicMock()
    mock_response_gdp.raise_for_status = MagicMock()
    mock_response_gdp.json.return_value = gdp_json

    mock_response_rate = MagicMock()
    mock_response_rate.raise_for_status = MagicMock()
    mock_response_rate.json.return_value = rate_json

    responses = [mock_response_gdp, mock_response_rate]

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_get(url, params):
        nonlocal call_count
        resp = responses[call_count % 2]
        call_count += 1
        return resp

    mock_client.get = fake_get

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await detector._fetch_economic_indicators()

    assert result["gdp"] == {"date": "2025-10-01", "value": "23500.0"}
    assert result["fed_rate"] == {"date": "2025-12-01", "value": "5.33"}


@pytest.mark.asyncio
async def test_fetch_economic_indicators_handles_http_error():
    detector = RegimeDetector(alpha_vantage_key="AV-KEY")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await detector._fetch_economic_indicators()

    assert result["gdp"] is None
    assert result["fed_rate"] is None


# ---------------------------------------------------------------------------
# RegimeSnapshot.economic_data in to_dict()
# ---------------------------------------------------------------------------


def test_regime_snapshot_to_dict_includes_economic_data():
    snap = RegimeSnapshot(
        regime=MarketRegime.SIDEWAYS,
        detected_at=datetime.now(timezone.utc),
        economic_data={
            "gdp": {"date": "2025-10-01", "value": "23500.0"},
            "fed_rate": None,
        },
    )
    d = snap.to_dict()
    assert "economic_data" in d
    assert d["economic_data"]["gdp"]["date"] == "2025-10-01"


def test_regime_snapshot_to_dict_economic_data_none_by_default():
    snap = RegimeSnapshot(
        regime=MarketRegime.UNKNOWN,
        detected_at=datetime.now(timezone.utc),
    )
    d = snap.to_dict()
    assert d["economic_data"] is None
