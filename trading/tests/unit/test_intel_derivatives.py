# trading/tests/unit/test_intel_derivatives.py
"""Tests for DerivativesProvider -- funding rate + open interest signals."""

import pytest
from unittest.mock import AsyncMock, patch

from intelligence.providers.derivatives import DerivativesProvider


# ── High positive funding = bearish ──────────────────────────────────────

@pytest.mark.asyncio
async def test_high_positive_funding_bearish():
    """Funding rate 0.08% (>0.05%) per 8h = overleveraged longs -> negative score."""
    provider = DerivativesProvider()
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.0008),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=0.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=0.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.source == "derivatives"
    assert report.symbol == "BTCUSD"
    assert report.score < 0, "High positive funding should produce bearish (negative) score"
    assert report.score <= -0.25, "Score should reflect strong funding signal"
    assert report.veto is False


# ── High negative funding = bullish ──────────────────────────────────────

@pytest.mark.asyncio
async def test_high_negative_funding_bullish():
    """Funding rate -0.08% (<-0.05%) per 8h = overleveraged shorts -> positive score."""
    provider = DerivativesProvider()
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=-0.0008),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=0.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=0.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.score > 0, "High negative funding should produce bullish (positive) score"
    assert report.score >= 0.25
    assert report.veto is False


# ── OI confirms trend ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_oi_confirms_trend():
    """OI up + price up = trend confirmed -> positive boost."""
    provider = DerivativesProvider()
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.0),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=5.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=2.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.score > 0, "OI up + price up should confirm trend (positive)"
    assert report.score == pytest.approx(0.15, abs=0.01)


# ── OI diverges from price ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_oi_diverges_from_price():
    """OI down + price up = short covering, not real demand -> negative."""
    provider = DerivativesProvider()
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.0),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=-3.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=2.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.score < 0, "OI down + price up = short covering -> bearish"
    assert report.score == pytest.approx(-0.10, abs=0.01)


# ── OI up + price down = bearish new shorts ──────────────────────────────

@pytest.mark.asyncio
async def test_oi_up_price_down_bearish():
    """OI up + price down = new short positions opening -> bearish."""
    provider = DerivativesProvider()
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.0),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=5.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=-2.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.score < 0, "OI up + price down = bearish new shorts"
    assert report.score == pytest.approx(-0.15, abs=0.01)


# ── OI down + price down = capitulation ──────────────────────────────────

@pytest.mark.asyncio
async def test_oi_down_price_down_capitulation():
    """OI down + price down = capitulation, may reverse -> slight bullish."""
    provider = DerivativesProvider()
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.0),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=-3.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=-2.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.score > 0, "OI down + price down = capitulation -> slight bullish"
    assert report.score == pytest.approx(0.10, abs=0.01)


# ── Neutral funding = near-zero score ────────────────────────────────────

@pytest.mark.asyncio
async def test_neutral_funding_low_score():
    """Funding near zero + no OI signal -> near-zero score."""
    provider = DerivativesProvider()
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.00005),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=0.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=0.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert abs(report.score) < 0.05, "Neutral funding should produce near-zero score"


# ── Combined scoring ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_combined_scoring():
    """High positive funding + OI confirms bearish should stack."""
    provider = DerivativesProvider()
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.0008),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=5.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=-2.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    # Funding: -0.3 (high positive), OI up + price down: -0.15
    # Combined: -0.45
    assert report.score < -0.3, "Both signals bearish should combine for strong negative"
    assert report.score == pytest.approx(-0.45, abs=0.05)


# ── Exchange failure = graceful None ─────────────────────────────────────

@pytest.mark.asyncio
async def test_exchange_failure_returns_none():
    """If CCXT fails, return None gracefully."""
    provider = DerivativesProvider()
    with patch.object(
        provider, "_fetch_funding_rate",
        new_callable=AsyncMock,
        side_effect=Exception("Exchange timeout"),
    ):
        report = await provider.analyze("BTCUSD")
    assert report is None


# ── Never vetoes ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_never_vetoes():
    """Derivatives signals are informational -- never veto."""
    provider = DerivativesProvider()
    # Even with extreme values
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.005),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=50.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=-30.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.veto is False
    assert report.veto_reason is None


# ── Confidence scales with funding magnitude ─────────────────────────────

@pytest.mark.asyncio
async def test_confidence_scales_with_funding_magnitude():
    """Higher funding magnitude -> higher confidence."""
    provider = DerivativesProvider()

    # Low funding
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.00005),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=0.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=0.0),
    ):
        low_report = await provider.analyze("BTCUSD")

    # High funding
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.001),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=0.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=0.0),
    ):
        high_report = await provider.analyze("BTCUSD")

    assert low_report is not None and high_report is not None
    assert high_report.confidence > low_report.confidence, \
        "Extreme funding should produce higher confidence"
    assert low_report.confidence >= 0.5, "Base confidence should be at least 0.5"
    assert high_report.confidence <= 0.9, "Max confidence should not exceed 0.9"


# ── Name property ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_name_property():
    provider = DerivativesProvider()
    assert provider.name == "derivatives"


# ── Score clamping ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_clamped_to_range():
    """Score should always be in [-1, 1] even with extreme inputs."""
    provider = DerivativesProvider()
    with (
        patch.object(provider, "_fetch_funding_rate", new_callable=AsyncMock, return_value=0.01),
        patch.object(provider, "_fetch_oi_change_pct", new_callable=AsyncMock, return_value=100.0),
        patch.object(provider, "_fetch_price_change_pct", new_callable=AsyncMock, return_value=-50.0),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is not None
    assert -1.0 <= report.score <= 1.0
    assert 0.0 <= report.confidence <= 1.0
