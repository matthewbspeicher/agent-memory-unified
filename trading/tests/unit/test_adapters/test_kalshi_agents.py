"""Unit tests for Kalshi prediction market agent strategies."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from broker.models import LimitOrder, OrderSide, PredictionContract
from agents.models import AgentConfig, ActionLevel


def _make_config(strategy: str = "kalshi_news_arb", **params) -> AgentConfig:
    return AgentConfig(
        name=f"test_{strategy}",
        strategy=strategy,
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        parameters=params,
    )


def _make_contract(
    ticker: str = "MKT-001",
    title: str = "Will X happen?",
    category: str = "economics",
    yes_bid: int = 40,
    yes_ask: int = 42,
    volume_24h: int = 500,
    days_to_close: float = 30.0,
) -> PredictionContract:
    return PredictionContract(
        ticker=ticker,
        title=title,
        category=category,
        close_time=datetime.now(timezone.utc) + timedelta(days=days_to_close),
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        yes_last=(yes_bid + yes_ask) // 2,
        volume_24h=volume_24h,
    )


def _make_data_bus(contracts: list, anthropic_key: str = "sk-test") -> MagicMock:
    """Build a minimal DataBus mock with a KalshiDataSource attached."""
    source = AsyncMock()
    source.get_markets.return_value = contracts

    bus = MagicMock()
    bus._kalshi_source = source
    bus._anthropic_key = anthropic_key
    return bus


# ---------------------------------------------------------------------------
# KalshiTimeDecayAgent
# ---------------------------------------------------------------------------


class TestKalshiTimeDecayAgent:
    def _agent(self, **params):
        from strategies.kalshi_time_decay import KalshiTimeDecayAgent

        defaults = dict(max_days_to_close=3, max_price_cents=8, min_volume=100)
        cfg = _make_config("kalshi_time_decay", **{**defaults, **params})
        return KalshiTimeDecayAgent(cfg)

    @pytest.mark.asyncio
    async def test_emits_opportunity_for_qualifying_market(self):
        agent = self._agent()
        contract = _make_contract(
            yes_bid=6, yes_ask=8, days_to_close=1.5, volume_24h=300
        )
        bus = _make_data_bus([contract])

        opps = await agent.scan(bus)
        assert len(opps) == 1
        assert opps[0].signal == "SELL_YES"
        assert opps[0].suggested_trade is not None
        assert opps[0].suggested_trade.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_ignores_market_above_price_threshold(self):
        agent = self._agent(max_price_cents=8)
        contract = _make_contract(yes_bid=15, days_to_close=1.0, volume_24h=400)
        bus = _make_data_bus([contract])
        opps = await agent.scan(bus)
        assert len(opps) == 0

    @pytest.mark.asyncio
    async def test_ignores_market_too_far_from_expiry(self):
        agent = self._agent(max_days_to_close=3)
        contract = _make_contract(yes_bid=5, days_to_close=10.0, volume_24h=400)
        bus = _make_data_bus([contract])
        opps = await agent.scan(bus)
        assert len(opps) == 0

    @pytest.mark.asyncio
    async def test_ignores_illiquid_markets(self):
        agent = self._agent(min_volume=500)
        contract = _make_contract(yes_bid=5, days_to_close=1.0, volume_24h=50)
        bus = _make_data_bus([contract])
        opps = await agent.scan(bus)
        assert len(opps) == 0

    @pytest.mark.asyncio
    async def test_skips_when_no_kalshi_source(self):
        agent = self._agent()
        bus = MagicMock()
        bus._kalshi_source = None
        opps = await agent.scan(bus)
        assert opps == []

    @pytest.mark.asyncio
    async def test_limit_order_price_is_cents_probability(self):
        agent = self._agent()
        contract = _make_contract(
            yes_bid=7, yes_ask=9, days_to_close=2.0, volume_24h=1000
        )
        bus = _make_data_bus([contract])
        opps = await agent.scan(bus)
        assert len(opps) == 1
        order = opps[0].suggested_trade
        assert isinstance(order, LimitOrder)
        # Sell YES at yes_bid cents converted to probability
        assert order.limit_price == Decimal("7") / Decimal("100")


# ---------------------------------------------------------------------------
# KalshiCalibrationAgent
# ---------------------------------------------------------------------------


class TestKalshiCalibrationAgent:
    def _agent(self, **params):
        from strategies.kalshi_calibration import KalshiCalibrationAgent

        defaults = dict(threshold_cents=10, min_volume=100)
        cfg = _make_config("kalshi_calibration", **{**defaults, **params})
        return KalshiCalibrationAgent(cfg)

    @pytest.mark.asyncio
    async def test_emits_opportunity_when_gap_exceeds_threshold(self):
        agent = self._agent(threshold_cents=10)
        # Market is at 40¢; Metaculus says 60% → 20¢ gap, direction=YES
        contract = _make_contract(
            yes_bid=39,
            yes_ask=41,
            volume_24h=500,
            title="Will the Fed raise rates in 2026?",
        )
        bus = _make_data_bus([contract])

        metaculus_q = {
            "id": 1,
            "title": "Will the Fed raise interest rates in 2026?",
            "community_prediction": 0.60,
        }

        with patch(
            "strategies.kalshi_calibration._fetch_metaculus_questions",
            new=AsyncMock(return_value=[metaculus_q]),
        ):
            opps = await agent.scan(bus)

        assert len(opps) >= 1
        assert opps[0].signal == "YES"
        assert opps[0].suggested_trade.side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_no_opportunity_when_gap_below_threshold(self):
        agent = self._agent(threshold_cents=20)
        contract = _make_contract(
            yes_bid=55,
            yes_ask=57,
            volume_24h=500,
            title="Will the Fed raise rates in 2026?",
        )
        bus = _make_data_bus([contract])

        metaculus_q = {
            "id": 1,
            "title": "Will the Fed raise interest rates?",
            "community_prediction": 0.58,  # only 2¢ gap from 56¢ market mid
        }

        with patch(
            "strategies.kalshi_calibration._fetch_metaculus_questions",
            new=AsyncMock(return_value=[metaculus_q]),
        ):
            opps = await agent.scan(bus)

        assert len(opps) == 0

    @pytest.mark.asyncio
    async def test_no_opportunity_when_no_matching_metaculus_question(self):
        agent = self._agent()
        contract = _make_contract(
            yes_bid=40,
            yes_ask=42,
            volume_24h=500,
            title="Will a very niche obscure event happen?",
        )
        bus = _make_data_bus([contract])

        metaculus_q = {
            "id": 1,
            "title": "Something totally different about sports",
            "community_prediction": 0.80,
        }

        with patch(
            "strategies.kalshi_calibration._fetch_metaculus_questions",
            new=AsyncMock(return_value=[metaculus_q]),
        ):
            opps = await agent.scan(bus)

        # Similarity will be below 0.25 threshold → no match
        assert len(opps) == 0


# ---------------------------------------------------------------------------
# KalshiNewsArbAgent (mocking LLM)
# ---------------------------------------------------------------------------


class TestKalshiNewsArbAgent:
    def _agent(self, **params):
        from strategies.kalshi_news_arb import KalshiNewsArbAgent

        defaults = dict(
            threshold_cents=15, min_volume=100, max_markets_per_scan=10, rss_feeds=[]
        )
        cfg = _make_config("kalshi_news_arb", **{**defaults, **params})
        return KalshiNewsArbAgent(cfg)

    @pytest.mark.asyncio
    async def test_emits_opportunity_when_llm_prob_differs_enough(self):
        agent = self._agent(threshold_cents=15)
        contract = _make_contract(yes_bid=30, yes_ask=32, volume_24h=200)
        bus = _make_data_bus([contract], anthropic_key="sk-test")

        with patch(
            "strategies.kalshi_news_arb._llm_estimate_probability",
            new=AsyncMock(return_value=(0.55, 80, "test reasoning")),
        ):  # 55% vs 31% market mid → 24¢ gap
            opps = await agent.scan(bus)

        assert len(opps) == 1
        assert opps[0].signal == "YES"

    @pytest.mark.asyncio
    async def test_no_opportunity_when_gap_below_threshold(self):
        agent = self._agent(threshold_cents=15)
        contract = _make_contract(yes_bid=49, yes_ask=51, volume_24h=200)
        bus = _make_data_bus([contract], anthropic_key="sk-test")

        with patch(
            "strategies.kalshi_news_arb._llm_estimate_probability",
            new=AsyncMock(return_value=(0.52, 70, "test reasoning")),
        ):  # only 2¢ gap
            opps = await agent.scan(bus)

        assert len(opps) == 0

    @pytest.mark.asyncio
    async def test_signal_is_no_when_llm_prob_is_lower(self):
        agent = self._agent(threshold_cents=15)
        contract = _make_contract(yes_bid=70, yes_ask=72, volume_24h=200)
        bus = _make_data_bus([contract], anthropic_key="sk-test")

        with patch(
            "strategies.kalshi_news_arb._llm_estimate_probability",
            new=AsyncMock(return_value=(0.50, 75, "test reasoning")),
        ):  # 50% vs 71% → sell YES
            opps = await agent.scan(bus)

        assert len(opps) == 1
        assert opps[0].signal == "NO"
        assert opps[0].suggested_trade.side == OrderSide.SELL
