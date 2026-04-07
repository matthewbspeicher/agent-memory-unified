import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from intelligence.providers.risk_audit import RiskAuditProvider


@pytest.mark.asyncio
async def test_risk_audit_low_vol_no_veto():
    """Low volatility should not trigger veto."""
    provider = RiskAuditProvider(var_threshold_pct=5.0, horizon_days=5)

    with patch.object(
        provider, "_fetch_current_price", new_callable=AsyncMock, return_value=50000.0
    ):
        with patch.object(
            provider, "_fetch_volatility", new_callable=AsyncMock, return_value=0.10
        ):
            report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.source == "risk_audit"
    assert report.veto is False
    assert report.details["var_99_pct"] < 5.0


@pytest.mark.asyncio
async def test_risk_audit_high_vol_triggers_veto():
    """Very high volatility should trigger veto."""
    provider = RiskAuditProvider(var_threshold_pct=5.0, horizon_days=5)

    with patch.object(
        provider, "_fetch_current_price", new_callable=AsyncMock, return_value=50000.0
    ):
        with patch.object(
            provider, "_fetch_volatility", new_callable=AsyncMock, return_value=2.0
        ):
            report = await provider.analyze("BTCUSD")

    assert report is not None
    assert report.veto is True
    assert "exceeds" in report.veto_reason
    assert report.score < 0  # negative score for high risk


@pytest.mark.asyncio
async def test_risk_audit_api_failure():
    provider = RiskAuditProvider()

    with patch.object(
        provider,
        "_fetch_current_price",
        new_callable=AsyncMock,
        side_effect=Exception("no data"),
    ):
        report = await provider.analyze("BTCUSD")

    assert report is None


@pytest.mark.asyncio
async def test_risk_audit_zero_price():
    provider = RiskAuditProvider()

    with patch.object(
        provider, "_fetch_current_price", new_callable=AsyncMock, return_value=0.0
    ):
        with patch.object(
            provider, "_fetch_volatility", new_callable=AsyncMock, return_value=0.5
        ):
            report = await provider.analyze("BTCUSD")

    assert report is None


@pytest.mark.asyncio
async def test_risk_monte_carlo_deterministic_check():
    """Verify Monte Carlo returns reasonable structure."""
    result = RiskAuditProvider._run_monte_carlo(
        current_price=50000.0,
        volatility=0.5,
        horizon_days=1,
        simulations=1000,
    )
    assert "var_95" in result
    assert "var_99" in result
    assert "var_95_pct" in result
    assert "var_99_pct" in result
    assert result["current_price"] == 50000.0
    assert result["var_99"] >= result["var_95"]  # 99% VaR >= 95% VaR
    assert result["var_95"] > 0  # should have some risk
