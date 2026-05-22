"""Tests for PersonaPanelAgent — Step A of the architecture follow-up.

Covers:
1. Constructor validates the persona list (drops unknown, raises on empty).
2. _gather_opinion stamps the persona key onto the structured opinion.
3. _run_panel gathers opinions concurrently and feeds them to the judge.
4. Confidence blend matches DebateAnalystAgent's formula.
5. _to_opportunity carries dissenting/majority/panelist_signals into data.
6. Aborts when too few panelists produce opinions.
7. agents.paper.yaml's persona_panel entries load and register.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.models import ActionLevel, AgentConfig, TrustLevel
from broker.models import Symbol
from strategies.persona_panel import DEFAULT_PANEL, PersonaPanelAgent


def _config(
    personas: list[str] | None = None,
    max_symbols: int = 2,
    min_conf: float = 0.55,
) -> AgentConfig:
    params = {
        "max_symbols_per_scan": max_symbols,
        "min_confidence": min_conf,
    }
    if personas is not None:
        params["personas"] = personas
    return AgentConfig(
        name="test_panel",
        strategy="persona_panel",
        schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
        trust_level=TrustLevel.MONITORED,
        model="claude-sonnet-4-6",
        parameters=params,
        universe=["AAPL"],
    )


# ---------------------------------------------------------------------------
# 1. Constructor validation
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_default_panel_is_all_six(self):
        agent = PersonaPanelAgent(_config())
        assert agent._personas == DEFAULT_PANEL
        assert len(agent._personas) == 6

    def test_subset_panel(self):
        agent = PersonaPanelAgent(
            _config(personas=["buffett_value", "lynch_growth"])
        )
        assert agent._personas == ["buffett_value", "lynch_growth"]

    def test_unknown_persona_is_dropped(self):
        agent = PersonaPanelAgent(
            _config(personas=["buffett_value", "not_a_real_persona"])
        )
        assert agent._personas == ["buffett_value"]

    def test_all_unknown_raises(self):
        with pytest.raises(ValueError, match="no valid personas"):
            PersonaPanelAgent(_config(personas=["fake1", "fake2"]))

    def test_description_reflects_count(self):
        agent = PersonaPanelAgent(_config())
        assert "6 personas" in agent.description


# ---------------------------------------------------------------------------
# 2. _gather_opinion
# ---------------------------------------------------------------------------


class TestGatherOpinion:
    @pytest.mark.asyncio
    async def test_stamps_persona_key_on_opinion(self):
        agent = PersonaPanelAgent(_config(personas=["buffett_value"]))
        agent._llm = MagicMock()
        agent._llm.structured_complete = AsyncMock(
            return_value={
                "signal": "long",
                "confidence": 0.7,
                "reasoning": "Strong moat",
                "key_risks": ["regulatory"],
            }
        )

        out = await agent._gather_opinion(
            "buffett_value", "AAPL", "2026-05-22T14:00:00+00:00", "{}"
        )

        assert out is not None
        assert out["persona"] == "buffett_value"
        assert out["signal"] == "long"
        assert out["reasoning"] == "Strong moat"

    @pytest.mark.asyncio
    async def test_returns_none_when_llm_returns_garbage(self):
        agent = PersonaPanelAgent(_config(personas=["buffett_value"]))
        agent._llm = MagicMock()
        agent._llm.structured_complete = AsyncMock(return_value=None)
        out = await agent._gather_opinion(
            "buffett_value", "AAPL", "2026-05-22T14:00:00+00:00", "{}"
        )
        assert out is None

    @pytest.mark.asyncio
    async def test_returns_none_on_llm_exception(self):
        agent = PersonaPanelAgent(_config(personas=["buffett_value"]))
        agent._llm = MagicMock()
        agent._llm.structured_complete = AsyncMock(side_effect=RuntimeError("api down"))
        out = await agent._gather_opinion(
            "buffett_value", "AAPL", "2026-05-22T14:00:00+00:00", "{}"
        )
        assert out is None


# ---------------------------------------------------------------------------
# 3. _run_panel — concurrency + judge
# ---------------------------------------------------------------------------


class TestRunPanel:
    @pytest.mark.asyncio
    async def test_aborts_when_too_few_opinions(self):
        agent = PersonaPanelAgent(
            _config(personas=["buffett_value", "lynch_growth", "marks_macro"])
        )
        agent._llm = MagicMock()
        # Two panelists fail, one succeeds — below the floor (max(2, n//2)=2)
        agent._llm.structured_complete = AsyncMock(
            side_effect=[
                {"signal": "long", "confidence": 0.7, "reasoning": "ok", "key_risks": []},
                None,
                None,
                # Judge would be the 4th call, but we should abort first.
            ]
        )
        verdict = await agent._run_panel(Symbol(ticker="AAPL"), "{}")
        assert verdict is None
        # Judge must not have been called
        assert agent._llm.structured_complete.await_count == 3

    @pytest.mark.asyncio
    async def test_happy_path_runs_panel_then_judge(self):
        agent = PersonaPanelAgent(
            _config(personas=["buffett_value", "lynch_growth"])
        )
        agent._llm = MagicMock()
        agent._llm.structured_complete = AsyncMock(
            side_effect=[
                {"signal": "long", "confidence": 0.7, "reasoning": "moat", "key_risks": []},
                {"signal": "long", "confidence": 0.65, "reasoning": "growth", "key_risks": []},
                {
                    "direction": "long",
                    "target_probability": 0.7,
                    "agreement": 0.9,
                    "reasoning": "Both bullish",
                    "majority_personas": ["buffett_value", "lynch_growth"],
                    "dissenting_personas": [],
                },
            ]
        )
        verdict = await agent._run_panel(Symbol(ticker="AAPL"), "{}")
        assert verdict is not None
        assert verdict["direction"] == "long"
        assert verdict["agreement"] == 0.9
        assert len(verdict["_opinions"]) == 2
        # 2 panelists + 1 judge
        assert agent._llm.structured_complete.await_count == 3


# ---------------------------------------------------------------------------
# 4. Confidence blend
# ---------------------------------------------------------------------------


class TestBlendConfidence:
    def test_strong_disagreement_strong_conviction_high(self):
        agent = PersonaPanelAgent(_config(personas=["buffett_value"]))
        # target_probability=0.9 → conviction=0.8
        # agreement=0.2 → disagreement=0.8
        # 0.6 * 0.8 + 0.4 * 0.8 = 0.8
        c = agent._blend_confidence(
            {"target_probability": 0.9, "agreement": 0.2}
        )
        assert abs(c - 0.8) < 1e-6

    def test_unanimous_panel_lowers_confidence(self):
        agent = PersonaPanelAgent(_config(personas=["buffett_value"]))
        # target_probability=0.7 → conviction=0.4
        # agreement=1.0 → disagreement=0
        # 0.6 * 0.4 + 0.4 * 0 = 0.24
        c = agent._blend_confidence(
            {"target_probability": 0.7, "agreement": 1.0}
        )
        assert abs(c - 0.24) < 1e-6

    def test_handles_missing_fields(self):
        agent = PersonaPanelAgent(_config(personas=["buffett_value"]))
        # Both default to 0.5
        c = agent._blend_confidence({})
        # conviction=0, disagreement=0.5 → 0.6*0 + 0.4*0.5 = 0.2
        assert abs(c - 0.2) < 1e-6

    def test_handles_garbage_input(self):
        agent = PersonaPanelAgent(_config(personas=["buffett_value"]))
        assert agent._blend_confidence({"target_probability": "abc"}) == 0.0


# ---------------------------------------------------------------------------
# 5. _to_opportunity carries panel metadata
# ---------------------------------------------------------------------------


class TestToOpportunity:
    def test_carries_panel_metadata(self):
        agent = PersonaPanelAgent(
            _config(personas=["buffett_value", "lynch_growth"])
        )
        verdict = {
            "direction": "long",
            "target_probability": 0.7,
            "agreement": 0.6,
            "reasoning": "Mostly bullish, Klarman dissents on debt",
            "majority_personas": ["buffett_value", "lynch_growth"],
            "dissenting_personas": ["klarman_distressed"],
            "_opinions": [
                {"persona": "buffett_value", "signal": "long"},
                {"persona": "lynch_growth", "signal": "long"},
                {"persona": "klarman_distressed", "signal": "flat"},
            ],
        }
        opp = agent._to_opportunity(Symbol(ticker="AAPL"), verdict, 0.62, "{}")
        assert opp.signal == "PANEL_LONG"
        assert opp.confidence == 0.62
        assert opp.data["agreement"] == 0.6
        assert opp.data["majority_personas"] == ["buffett_value", "lynch_growth"]
        assert opp.data["dissenting_personas"] == ["klarman_distressed"]
        assert opp.data["panelist_count"] == 3
        assert opp.data["panelist_signals"] == [
            {"persona": "buffett_value", "signal": "long"},
            {"persona": "lynch_growth", "signal": "long"},
            {"persona": "klarman_distressed", "signal": "flat"},
        ]
        assert opp.expires_at is not None
        assert opp.timestamp.tzinfo is not None  # UTC

    def test_short_signal(self):
        agent = PersonaPanelAgent(_config(personas=["buffett_value"]))
        verdict = {
            "direction": "short",
            "target_probability": 0.3,
            "agreement": 0.5,
            "reasoning": "x",
            "majority_personas": [],
            "dissenting_personas": [],
        }
        opp = agent._to_opportunity(Symbol(ticker="AAPL"), verdict, 0.6, "{}")
        assert opp.signal == "PANEL_SHORT"


# ---------------------------------------------------------------------------
# 6. YAML registration
# ---------------------------------------------------------------------------


class TestPanelYAMLLoads:
    def test_paper_yaml_loads_panel_entries(self):
        from agents.config import load_agents_config

        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "agents.paper.yaml"
        agents = load_agents_config(path=str(path))
        by_name = {a.config.name: a for a in agents}

        assert "persona_panel_equities" in by_name
        assert "persona_panel_crypto" in by_name

        eq = by_name["persona_panel_equities"]
        assert isinstance(eq, PersonaPanelAgent)
        assert eq._personas == DEFAULT_PANEL  # all 6
        assert eq._max_symbols == 2

        cr = by_name["persona_panel_crypto"]
        assert isinstance(cr, PersonaPanelAgent)
        assert cr._personas == ["marks_macro", "lynch_growth", "klarman_distressed"]
