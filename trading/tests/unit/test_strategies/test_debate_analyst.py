from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.models import ActionLevel, AgentConfig
from broker.models import Symbol


def _cfg(**overrides) -> AgentConfig:
    params = {
        "rounds": 2,
        "max_symbols_per_scan": 2,
        "min_confidence": 0.55,
        "conviction_weight": 0.6,
    }
    params.update(overrides.pop("parameters", {}))
    return AgentConfig(
        name="debate_test",
        strategy="debate_analyst",
        schedule="cron",
        cron="0 14 * * 1-5",
        action_level=ActionLevel.NOTIFY,
        universe=["NVDA", "AAPL"],
        parameters=params,
        **overrides,
    )


def _llm_stub(
    bull_text: str = "Bull case.",
    bear_text: str = "Bear case.",
    verdict: dict | None = None,
) -> MagicMock:
    llm = MagicMock()
    llm.chat = AsyncMock(
        side_effect=lambda system, messages, max_tokens: MagicMock(
            text=bull_text if "bull" in system.lower() else bear_text
        )
    )
    llm.structured_complete = AsyncMock(return_value=verdict)
    return llm


def _data_stub() -> MagicMock:
    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="NVDA"), Symbol(ticker="AAPL")])
    data.get_market_summary = AsyncMock(return_value={"symbol": "NVDA", "price": 850, "rsi_14": 62})
    data.get_key_levels = AsyncMock(return_value={"pivot": 840, "r1": 860, "s1": 820})
    data.get_volatility_summary = AsyncMock(return_value={"atr_14": 12.4})
    return data


async def test_scan_emits_opportunity_when_verdict_is_confident():
    from strategies.debate_analyst import DebateAnalystAgent

    verdict = {
        "direction": "long",
        "target_probability": 0.78,
        "agreement": 0.2,  # bull and bear disagreed → strong signal
        "reasoning": "Bull's earnings-beat argument outweighed bear's stretched-valuation rebuttal.",
        "bull_strongest": "Record data-center demand drove the last two beats.",
        "bear_strongest": "Forward P/E at 40 vs 5y median 28.",
    }
    agent = DebateAnalystAgent(_cfg(parameters={"max_symbols_per_scan": 1}), llm_client=_llm_stub(verdict=verdict))
    opps = await agent.scan(_data_stub())

    assert len(opps) == 1
    opp = opps[0]
    assert opp.signal == "DEBATE_LONG"
    # conviction = |0.78 - 0.5| * 2 = 0.56; disagreement = 1 - 0.2 = 0.8
    # confidence = 0.6 * 0.56 + 0.4 * 0.8 = 0.656
    assert 0.64 < opp.confidence < 0.68
    assert opp.data["direction"] == "long"
    assert opp.data["agreement"] == 0.2
    assert opp.data["debate_rounds"] == 2


async def test_scan_drops_low_confidence_verdict():
    from strategies.debate_analyst import DebateAnalystAgent

    # Both sides agreed and conviction is modest → confidence below floor.
    verdict = {
        "direction": "long",
        "target_probability": 0.55,
        "agreement": 0.9,
        "reasoning": "Both sides saw it going up.",
        "bull_strongest": "x",
        "bear_strongest": "y",
    }
    agent = DebateAnalystAgent(
        _cfg(parameters={"max_symbols_per_scan": 1, "min_confidence": 0.55}),
        llm_client=_llm_stub(verdict=verdict),
    )
    opps = await agent.scan(_data_stub())
    assert opps == []


async def test_scan_drops_flat_verdict_even_when_confident():
    from strategies.debate_analyst import DebateAnalystAgent

    verdict = {
        "direction": "flat",
        "target_probability": 0.9,
        "agreement": 0.1,
        "reasoning": "Evidence is strong that nothing moves.",
        "bull_strongest": "x",
        "bear_strongest": "y",
    }
    agent = DebateAnalystAgent(
        _cfg(parameters={"max_symbols_per_scan": 1}),
        llm_client=_llm_stub(verdict=verdict),
    )
    opps = await agent.scan(_data_stub())
    assert opps == []


async def test_scan_returns_empty_when_judge_returns_none():
    from strategies.debate_analyst import DebateAnalystAgent

    agent = DebateAnalystAgent(
        _cfg(parameters={"max_symbols_per_scan": 1}),
        llm_client=_llm_stub(verdict=None),
    )
    opps = await agent.scan(_data_stub())
    assert opps == []


async def test_scan_returns_empty_when_bull_turn_is_empty():
    from strategies.debate_analyst import DebateAnalystAgent

    agent = DebateAnalystAgent(
        _cfg(parameters={"max_symbols_per_scan": 1}),
        llm_client=_llm_stub(bull_text="", verdict={"direction": "long", "target_probability": 0.9, "agreement": 0.1, "reasoning": "r", "bull_strongest": "a", "bear_strongest": "b"}),
    )
    opps = await agent.scan(_data_stub())
    assert opps == []


async def test_scan_caps_at_max_symbols_per_scan():
    from strategies.debate_analyst import DebateAnalystAgent

    verdict = {
        "direction": "long",
        "target_probability": 0.78,
        "agreement": 0.2,
        "reasoning": "r",
        "bull_strongest": "a",
        "bear_strongest": "b",
    }
    agent = DebateAnalystAgent(
        _cfg(parameters={"max_symbols_per_scan": 1}),  # cap = 1
        llm_client=_llm_stub(verdict=verdict),
    )
    data = _data_stub()
    # universe advertises 2 symbols; agent should stop after 1
    opps = await agent.scan(data)
    assert len(opps) == 1
    assert data.get_market_summary.await_count == 1


async def test_confidence_blend_formula_matches_spec():
    from strategies.debate_analyst import DebateAnalystAgent

    agent = DebateAnalystAgent(_cfg(parameters={"conviction_weight": 0.6}), llm_client=MagicMock())

    # p=1.0, agreement=0 → conviction=1, disagreement=1 → confidence=1.0
    assert agent._blend_confidence(
        {"direction": "long", "target_probability": 1.0, "agreement": 0.0}
    ) == pytest.approx(1.0)

    # p=0.5, agreement=1.0 → conviction=0, disagreement=0 → confidence=0.0
    assert agent._blend_confidence(
        {"direction": "flat", "target_probability": 0.5, "agreement": 1.0}
    ) == pytest.approx(0.0)


async def test_confidence_blend_handles_bad_values():
    from strategies.debate_analyst import DebateAnalystAgent

    agent = DebateAnalystAgent(_cfg(), llm_client=MagicMock())
    assert agent._blend_confidence({"direction": "long", "target_probability": None, "agreement": "oops"}) == 0.0


async def test_context_bundle_survives_missing_optional_fields():
    from strategies.debate_analyst import DebateAnalystAgent

    agent = DebateAnalystAgent(_cfg(parameters={"max_symbols_per_scan": 1}),
                               llm_client=_llm_stub(verdict={
                                   "direction": "short", "target_probability": 0.8,
                                   "agreement": 0.2, "reasoning": "r",
                                   "bull_strongest": "a", "bear_strongest": "b"}))
    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="NVDA")])
    data.get_market_summary = AsyncMock(return_value={"symbol": "NVDA", "price": 850})
    data.get_key_levels = AsyncMock(side_effect=Exception("no levels"))
    data.get_volatility_summary = AsyncMock(side_effect=Exception("no vol"))

    opps = await agent.scan(data)
    assert len(opps) == 1
    assert opps[0].signal == "DEBATE_SHORT"
