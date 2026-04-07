"""Tests for FundingRateArbAgent — delta-neutral funding rate arbitrage."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.models import ActionLevel, AgentConfig
from strategies.funding_rate_arb import FundingRateArbAgent


def _make_config(**overrides) -> AgentConfig:
    defaults = dict(
        name="funding_rate_test",
        strategy="funding_rate_arb",
        schedule="continuous",
        interval=300,
        action_level=ActionLevel.SUGGEST_TRADE,
        parameters={
            "symbols": ["BTCUSD", "ETHUSD"],
            "min_annualized_rate": 0.20,
            "exit_rate": 0.05,
            "exchange": "binance",
        },
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


@pytest.fixture
def agent():
    return FundingRateArbAgent(_make_config())


@pytest.fixture
def mock_data_bus():
    return MagicMock()


# ── High positive funding → BUY signal ──────────────────────────────────


@pytest.mark.asyncio
async def test_high_positive_funding_emits_buy(agent, mock_data_bus):
    """When annualized funding rate > threshold, emit BUY (long spot + short perp)."""
    # funding_rate = 0.0001 → annualized = 0.0001 * 3 * 365 = 0.1095 (10.95%) — below threshold
    # funding_rate = 0.0003 → annualized = 0.0003 * 3 * 365 = 0.3285 (32.85%) — above 20%
    agent._fetch_funding_rate = AsyncMock(return_value=0.0003)

    opps = await agent.scan(mock_data_bus)

    # Should have opportunities for both BTCUSD and ETHUSD
    assert len(opps) == 2
    for opp in opps:
        assert opp.signal == "BUY"
        assert opp.confidence > 0
        assert opp.data["funding_rate"] == 0.0003
        assert opp.data["annualized_rate"] == pytest.approx(0.3285, rel=1e-3)
        assert opp.symbol.asset_type.value == "CRYPTO"


# ── High negative funding → SELL signal ──────────────────────────────────


@pytest.mark.asyncio
async def test_high_negative_funding_emits_sell(agent, mock_data_bus):
    """When annualized funding rate < -threshold, emit SELL (short spot + long perp)."""
    agent._fetch_funding_rate = AsyncMock(return_value=-0.0003)

    opps = await agent.scan(mock_data_bus)

    assert len(opps) == 2
    for opp in opps:
        assert opp.signal == "SELL"
        assert opp.confidence > 0
        assert opp.data["funding_rate"] == -0.0003
        assert opp.data["annualized_rate"] == pytest.approx(-0.3285, rel=1e-3)


# ── Low funding (within threshold) → no signal ──────────────────────────


@pytest.mark.asyncio
async def test_low_funding_no_signal(agent, mock_data_bus):
    """When abs(annualized) < threshold, no opportunities emitted."""
    # 0.0001 * 3 * 365 = 0.1095 → 10.95% < 20% threshold
    agent._fetch_funding_rate = AsyncMock(return_value=0.0001)

    opps = await agent.scan(mock_data_bus)
    assert len(opps) == 0


# ── Very high funding → confidence capped at 1.0 ────────────────────────


@pytest.mark.asyncio
async def test_very_high_funding_caps_confidence(agent, mock_data_bus):
    """Confidence should never exceed 1.0 even with extreme funding rates."""
    # 0.005 * 3 * 365 = 5.475 → 547.5% annualized
    agent._fetch_funding_rate = AsyncMock(return_value=0.005)

    opps = await agent.scan(mock_data_bus)

    assert len(opps) == 2
    for opp in opps:
        assert opp.confidence <= 1.0


# ── Confidence scales proportionally ────────────────────────────────────


@pytest.mark.asyncio
async def test_confidence_scales_with_rate(mock_data_bus):
    """Higher funding rate → higher confidence."""
    cfg = _make_config()

    agent_low = FundingRateArbAgent(cfg)
    agent_low._fetch_funding_rate = AsyncMock(return_value=0.00025)  # ~27.4% annualized

    agent_high = FundingRateArbAgent(cfg)
    agent_high._fetch_funding_rate = AsyncMock(return_value=0.0005)  # ~54.75% annualized

    opps_low = await agent_low.scan(mock_data_bus)
    opps_high = await agent_high.scan(mock_data_bus)

    assert len(opps_low) > 0
    assert len(opps_high) > 0
    assert opps_high[0].confidence > opps_low[0].confidence


# ── Exchange failure → graceful degradation ──────────────────────────────


@pytest.mark.asyncio
async def test_exchange_failure_returns_empty(agent, mock_data_bus):
    """If CCXT raises, return empty list (no crash)."""
    agent._fetch_funding_rate = AsyncMock(side_effect=Exception("Exchange down"))

    opps = await agent.scan(mock_data_bus)
    assert opps == []


# ── Symbol mapping ───────────────────────────────────────────────────────


def test_symbol_mapping(agent):
    """BTCUSD → BTC/USDT:USDT for Binance perpetual."""
    assert agent._map_symbol("BTCUSD") == "BTC/USDT:USDT"
    assert agent._map_symbol("ETHUSD") == "ETH/USDT:USDT"
    assert agent._map_symbol("SOLUSD") == "SOL/USDT:USDT"


# ── Custom parameters ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_threshold(mock_data_bus):
    """Agent respects custom min_annualized_rate parameter."""
    cfg = _make_config(
        parameters={
            "symbols": ["BTCUSD"],
            "min_annualized_rate": 0.10,  # 10% threshold
            "exit_rate": 0.02,
            "exchange": "binance",
        }
    )
    agent = FundingRateArbAgent(cfg)
    # 0.0001 * 3 * 365 = 10.95% > 10% custom threshold
    agent._fetch_funding_rate = AsyncMock(return_value=0.0001)

    opps = await agent.scan(mock_data_bus)
    assert len(opps) == 1
    assert opps[0].signal == "BUY"


# ── Description property ─────────────────────────────────────────────────


def test_description(agent):
    """Agent has a meaningful description."""
    desc = agent.description
    assert "funding" in desc.lower()
