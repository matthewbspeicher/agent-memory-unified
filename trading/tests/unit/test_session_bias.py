"""Tests for the session bias generator (brief/session_bias.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from brief.session_bias import (
    SessionBiasGenerator,
    SessionBiasReport,
    SymbolBias,
)
from brief.rules_loader import TradingRules, SessionBiasConfig, RiskOverlay


# --- Fixtures ---


@dataclass
class FakeQuote:
    last: float = 65000.0
    bid: float = 64990.0
    ask: float = 65010.0
    change_percent: float = 2.5


@dataclass
class FakeMACD:
    macd_line: float = 150.0
    signal_line: float = 120.0
    histogram: float = 30.0


@dataclass
class FakeBollinger:
    upper: float = 68000.0
    middle: float = 65000.0
    lower: float = 62000.0


def _make_rules() -> TradingRules:
    return TradingRules(
        watchlist={"crypto": ["BTCUSD", "ETHUSD"]},
        session_bias=SessionBiasConfig(
            timeframes=["1d"],
            indicators=["rsi_14", "ema_200", "macd"],
            bullish_criteria=["price above EMA 200"],
            bearish_criteria=["price below EMA 200"],
            neutral_criteria=["no clear trend"],
        ),
        risk_overlay=RiskOverlay(),
    )


def _make_data_bus():
    bus = AsyncMock()
    bus.get_quote = AsyncMock(return_value=FakeQuote())
    bus.get_rsi = AsyncMock(return_value=58.0)
    bus.get_ema = AsyncMock(side_effect=lambda sym, period: 60000.0 if period == 200 else 64000.0)
    bus.get_macd = AsyncMock(return_value=FakeMACD())
    bus.get_bollinger = AsyncMock(return_value=FakeBollinger())
    return bus


def _make_db():
    db = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=cursor)
    db.commit = AsyncMock()
    return db


def _make_llm(response_text: str):
    llm = AsyncMock()
    result = MagicMock()
    result.text = response_text
    llm.complete = AsyncMock(return_value=result)
    return llm


# --- Tests ---


class TestSymbolBias:
    def test_dataclass_fields(self):
        sb = SymbolBias(
            symbol="BTCUSD",
            bias="bullish",
            confidence=0.8,
            reasoning="Strong momentum",
        )
        assert sb.symbol == "BTCUSD"
        assert sb.bias == "bullish"
        assert sb.confidence == 0.8


class TestSessionBiasReport:
    def test_for_symbol(self):
        report = SessionBiasReport(
            date="2026-04-08",
            generated_at="2026-04-08T08:00:00",
            overall_bias="bullish",
            symbols=[
                SymbolBias(symbol="BTCUSD", bias="bullish", confidence=0.8),
                SymbolBias(symbol="ETHUSD", bias="neutral", confidence=0.5),
            ],
        )
        assert report.for_symbol("BTCUSD").bias == "bullish"
        assert report.for_symbol("ETHUSD").confidence == 0.5
        assert report.for_symbol("SOLUSD") is None

    def test_to_agent_context(self):
        report = SessionBiasReport(
            date="2026-04-08",
            generated_at="2026-04-08T08:00:00",
            overall_bias="bullish",
            symbols=[
                SymbolBias(symbol="BTCUSD", bias="bullish", confidence=0.75, reasoning="RSI rising"),
            ],
            risk_notes=["High correlation"],
        )
        ctx = report.to_agent_context()
        assert "Session Bias (2026-04-08): bullish" in ctx
        assert "BTCUSD: bullish (conf=75%)" in ctx
        assert "High correlation" in ctx

    def test_to_dict(self):
        report = SessionBiasReport(
            date="2026-04-08",
            generated_at="2026-04-08T08:00:00",
            overall_bias="neutral",
            symbols=[],
        )
        d = report.to_dict()
        assert d["overall_bias"] == "neutral"
        assert d["symbols"] == []


class TestSessionBiasGenerator:
    @pytest.mark.asyncio
    async def test_fallback_bias_when_no_llm(self):
        rules_loader = MagicMock()
        rules_loader.get.return_value = _make_rules()

        gen = SessionBiasGenerator(
            db=_make_db(),
            data_bus=_make_data_bus(),
            llm=_make_llm(""),  # empty LLM response
            rules_loader=rules_loader,
        )
        report = await gen.generate()

        assert isinstance(report, SessionBiasReport)
        assert len(report.symbols) == 2
        assert report.symbols[0].symbol == "BTCUSD"
        # Price (65000) > EMA200 (60000), RSI 58, MACD positive → bullish
        assert report.symbols[0].bias == "bullish"

    @pytest.mark.asyncio
    async def test_parses_llm_json_response(self):
        llm_response = json.dumps({
            "symbols": [
                {
                    "symbol": "BTCUSD",
                    "bias": "bullish",
                    "confidence": 0.85,
                    "key_levels": {"support": 62000, "resistance": 68000},
                    "reasoning": "Strong uptrend"
                },
                {
                    "symbol": "ETHUSD",
                    "bias": "neutral",
                    "confidence": 0.5,
                    "key_levels": {},
                    "reasoning": "Consolidating"
                },
            ],
            "overall_bias": "bullish",
            "risk_notes": ["Watch for BTC dominance shift"],
        })

        rules_loader = MagicMock()
        rules_loader.get.return_value = _make_rules()

        gen = SessionBiasGenerator(
            db=_make_db(),
            data_bus=_make_data_bus(),
            llm=_make_llm(llm_response),
            rules_loader=rules_loader,
        )
        report = await gen.generate()

        assert report.overall_bias == "bullish"
        assert len(report.symbols) == 2
        assert report.symbols[0].confidence == 0.85
        assert report.symbols[0].key_levels["support"] == 62000
        assert "BTC dominance" in report.risk_notes[0]

    @pytest.mark.asyncio
    async def test_get_active_bias_returns_none_when_empty(self):
        gen = SessionBiasGenerator(
            db=_make_db(),
            data_bus=_make_data_bus(),
            rules_loader=MagicMock(),
        )
        bias = await gen.get_active_bias()
        assert bias is None

    @pytest.mark.asyncio
    async def test_caches_after_generate(self):
        rules_loader = MagicMock()
        rules_loader.get.return_value = _make_rules()

        gen = SessionBiasGenerator(
            db=_make_db(),
            data_bus=_make_data_bus(),
            llm=_make_llm(""),
            rules_loader=rules_loader,
        )
        report = await gen.generate()
        cached = await gen.get_active_bias()

        assert cached is report
