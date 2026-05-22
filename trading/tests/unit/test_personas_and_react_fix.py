"""Tests for Step 4 of the May-2026 architecture plan:

1. ``react_analyst.py`` bug fix — ``_generate_action`` and
   ``_generate_opportunity`` previously hard-coded the system prompt
   and ignored ``config.system_prompt``. Persona-shaped configs now
   take effect.

2. ``LLMAnalystAgent._build_market_summary`` — when
   ``parameters.consume_sentiment=True`` is set, the market summary
   appends the latest ``intel_sentiment`` topic value per symbol
   (ADR-0011).

3. The six new persona YAML entries in ``agents.paper.yaml`` parse
   cleanly under the existing config loader.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.models import (
    ActionLevel,
    AgentConfig,
    AgentSignal,
    TrustLevel,
)
from broker.models import Symbol
from data.signal_bus import SignalBus
from strategies.llm_analyst import LLMAnalystAgent
from strategies.react_analyst import ReactAnalystAgent


# ---------------------------------------------------------------------------
# 1. ReactAnalyst persona system-prompt fix
# ---------------------------------------------------------------------------


def _make_react_agent(system_prompt: str | None = None) -> ReactAnalystAgent:
    config = AgentConfig(
        name="test_react",
        strategy="react_analyst",
        schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
        trust_level=TrustLevel.MONITORED,
        model="claude-sonnet-4-6",
        system_prompt=system_prompt,
        parameters={"max_iterations": 5, "confidence_threshold": 0.6},
        universe=["BTCUSD"],
    )
    return ReactAnalystAgent(config)


class TestReactAnalystSystemPromptFix:
    """Verify _generate_action and _generate_opportunity now layer
    config.system_prompt onto the hard-coded JSON-only directive."""

    @pytest.mark.asyncio
    async def test_generate_action_uses_persona_when_set(self):
        agent = _make_react_agent(
            system_prompt="You are Warren Buffett. Apply long-horizon value investing."
        )
        agent._llm_client = MagicMock()
        agent._llm_client.chat = AsyncMock(
            return_value=SimpleNamespace(text='{"type": "final_answer"}')
        )

        await agent._generate_action(
            thought="Market analysis", context={"symbol": "BTCUSD"}
        )

        # The system kwarg should now lead with the Buffett persona then
        # the JSON-only directive.
        call_kwargs = agent._llm_client.chat.call_args.kwargs
        system = call_kwargs["system"]
        assert system.startswith("You are Warren Buffett")
        assert "JSON only" in system

    @pytest.mark.asyncio
    async def test_generate_action_falls_back_to_directive_only(self):
        """No system_prompt set → only the JSON-only directive (no leading newlines)."""
        agent = _make_react_agent(system_prompt=None)
        agent._llm_client = MagicMock()
        agent._llm_client.chat = AsyncMock(
            return_value=SimpleNamespace(text='{"type": "final_answer"}')
        )

        await agent._generate_action(
            thought="Market analysis", context={"symbol": "BTCUSD"}
        )

        system = agent._llm_client.chat.call_args.kwargs["system"]
        # Hard-coded directive intact; no persona prefix.
        assert system == "You are a trading analyst. Respond with valid JSON only."

    @pytest.mark.asyncio
    async def test_generate_opportunity_uses_persona_when_set(self):
        agent = _make_react_agent(
            system_prompt="You are Charlie Munger. Invert: what would make this fail?"
        )
        agent._llm_client = MagicMock()
        agent._llm_client.chat = AsyncMock(
            return_value=SimpleNamespace(
                text='{"signal": "BUY", "confidence": 0.8, "reasoning": "x", "direction": "bullish"}'
            )
        )

        await agent._generate_opportunity(
            symbol=Symbol(ticker="BTCUSD"),
            trace=[],
            confidence_threshold=0.6,
        )

        system = agent._llm_client.chat.call_args.kwargs["system"]
        assert system.startswith("You are Charlie Munger")
        assert "JSON only" in system


# ---------------------------------------------------------------------------
# 2. LLMAnalystAgent sentiment injection (ADR-0011)
# ---------------------------------------------------------------------------


def _make_llm_agent(consume_sent: bool = False) -> LLMAnalystAgent:
    config = AgentConfig(
        name="test_persona",
        strategy="llm_analyst",
        schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
        trust_level=TrustLevel.MONITORED,
        model="claude-sonnet-4-6",
        system_prompt="You are a value investor.",
        parameters={"consume_sentiment": consume_sent, "sentiment_max_age_seconds": 600},
        universe=["BTCUSD"],
    )
    return LLMAnalystAgent(config)


class _DummyDataBus:
    """Minimal DataBus stub providing get_quote and get_rsi."""

    def __init__(self, quotes: dict, rsis: dict):
        self._quotes = quotes
        self._rsis = rsis

    async def get_quote(self, symbol):
        q = self._quotes.get(symbol.ticker)
        return SimpleNamespace(last=q["last"], volume=q["volume"]) if q else None

    async def get_rsi(self, symbol, period):
        return self._rsis.get(symbol.ticker, 50.0)


class TestLLMAnalystSentimentInjection:
    @pytest.mark.asyncio
    async def test_no_sentiment_when_flag_false(self):
        agent = _make_llm_agent(consume_sent=False)
        agent.signal_bus = SignalBus()
        # Even with a fresh sentiment signal on the bus, the summary should
        # not mention it when the flag is off.
        await agent.signal_bus.publish(
            AgentSignal(
                source_agent="intelligence_layer",
                signal_type="intel_sentiment",
                payload={
                    "symbol": "BTCUSD",
                    "score": 0.5,
                    "confidence": 0.8,
                    "sources": {},
                },
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
        )
        data = _DummyDataBus(
            quotes={"BTCUSD": {"last": 65000.0, "volume": 12345}},
            rsis={"BTCUSD": 55.0},
        )
        summary = await agent._build_market_summary(data, [Symbol(ticker="BTCUSD")])
        assert "BTCUSD" in summary
        assert "sentiment_score" not in summary

    @pytest.mark.asyncio
    async def test_sentiment_appended_when_fresh(self):
        agent = _make_llm_agent(consume_sent=True)
        agent.signal_bus = SignalBus()
        await agent.signal_bus.publish(
            AgentSignal(
                source_agent="intelligence_layer",
                signal_type="intel_sentiment",
                payload={
                    "symbol": "BTCUSD",
                    "score": 0.42,
                    "confidence": 0.75,
                    "sources": {"fear_greed_value": 25},
                },
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
        )
        data = _DummyDataBus(
            quotes={"BTCUSD": {"last": 65000.0, "volume": 12345}},
            rsis={"BTCUSD": 55.0},
        )
        summary = await agent._build_market_summary(data, [Symbol(ticker="BTCUSD")])
        assert "sentiment_score=+0.42" in summary
        assert "conf 75%" in summary

    @pytest.mark.asyncio
    async def test_no_sentiment_when_symbol_has_no_topic_entry(self):
        """Equities like AAPL never appear on the topic — summary just
        omits the sentiment column."""
        agent = _make_llm_agent(consume_sent=True)
        agent.signal_bus = SignalBus()
        data = _DummyDataBus(
            quotes={"AAPL": {"last": 180.0, "volume": 99999}},
            rsis={"AAPL": 60.0},
        )
        summary = await agent._build_market_summary(data, [Symbol(ticker="AAPL")])
        assert "AAPL" in summary
        assert "sentiment_score" not in summary


# ---------------------------------------------------------------------------
# 3. Persona YAML entries parse via config loader
# ---------------------------------------------------------------------------


class TestPersonaYAMLLoads:
    def test_paper_yaml_loads_six_personas(self):
        from agents.config import load_agents_config

        # Resolve agents.paper.yaml relative to this test file's repo.
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "agents.paper.yaml"
        assert path.exists(), f"missing {path}"

        # Load — populates the strategy registry implicitly via imports.
        agents = load_agents_config(path=str(path))
        configs = [a.config for a in agents]
        names = {c.name for c in configs}

        for persona in (
            "buffett_value",
            "graham_deep_value",
            "lynch_growth",
            "munger_quality",
            "klarman_distressed",
            "marks_macro",
        ):
            assert persona in names, f"persona {persona!r} missing from loaded configs"

    def test_persona_configs_have_system_prompts(self):
        from agents.config import load_agents_config

        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "agents.paper.yaml"
        agents = load_agents_config(path=str(path))
        configs = [a.config for a in agents]
        personas = {
            c.name: c
            for c in configs
            if c.name
            in (
                "buffett_value",
                "graham_deep_value",
                "lynch_growth",
                "munger_quality",
                "klarman_distressed",
                "marks_macro",
            )
        }

        # All 6 must have a non-empty system_prompt
        for name, cfg in personas.items():
            assert cfg.system_prompt, f"{name} missing system_prompt"
            assert len(cfg.system_prompt) > 50, f"{name} system_prompt suspiciously short"
            assert cfg.strategy == "llm"
            assert cfg.action_level == ActionLevel.NOTIFY
            assert cfg.trust_level == TrustLevel.MONITORED

    def test_at_least_three_personas_opt_into_sentiment(self):
        """Plan requires several personas to consume the sentiment topic
        so the Step 1 wiring isn't dead.  Buffett, Lynch, Klarman, Marks
        all opt in; Graham and Munger explicitly opt out (philosophically)."""
        from agents.config import load_agents_config

        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "agents.paper.yaml"
        agents = load_agents_config(path=str(path))
        configs = [a.config for a in agents]
        opted_in = [
            c.name
            for c in configs
            if c.name
            in (
                "buffett_value",
                "graham_deep_value",
                "lynch_growth",
                "munger_quality",
                "klarman_distressed",
                "marks_macro",
            )
            and bool(c.parameters.get("consume_sentiment"))
        ]
        assert len(opted_in) >= 3, f"only {opted_in} opt into sentiment"
