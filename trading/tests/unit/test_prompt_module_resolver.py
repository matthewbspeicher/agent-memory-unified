"""Tests for the ``module:`` sentinel in YAML ``system_prompt`` fields.

Resolver lives in ``trading/agents/config.py:_resolve_prompt_reference``.
It lets personas (and any future LLM agent) reference a Python module
constant instead of inlining a 200-word prompt block in YAML.

Covers:
1. ``module:dotted.module:CONSTANT`` references resolve to the string value.
2. Plain (non-prefixed) strings pass through unchanged.
3. None passes through unchanged.
4. Malformed references raise ValueError at load time (not at first scan).
5. The six persona YAML entries in ``agents.paper.yaml`` load via the
   sentinel and produce the exact same prompt text as the underlying
   ``personas.py`` constants — no copy drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.config import _resolve_prompt_reference, load_agents_config
from strategies.prompts.personas import (
    BUFFETT_VALUE,
    GRAHAM_DEEP_VALUE,
    KLARMAN_DISTRESSED,
    LYNCH_GROWTH,
    MARKS_MACRO,
    MUNGER_QUALITY,
    PERSONA_PROMPTS,
)


# ---------------------------------------------------------------------------
# 1-3. Resolver basic behaviour
# ---------------------------------------------------------------------------


class TestResolver:
    def test_resolves_module_reference(self):
        out = _resolve_prompt_reference(
            "module:strategies.prompts.personas:BUFFETT_VALUE"
        )
        assert out is BUFFETT_VALUE
        assert out.startswith("You are Warren Buffett.")

    def test_plain_string_passes_through(self):
        out = _resolve_prompt_reference("You are a trader.")
        assert out == "You are a trader."

    def test_none_passes_through(self):
        assert _resolve_prompt_reference(None) is None

    def test_empty_string_passes_through(self):
        assert _resolve_prompt_reference("") == ""

    def test_module_prefix_alone_raises(self):
        with pytest.raises(ValueError, match="must be"):
            _resolve_prompt_reference("module:no_colon_here")

    def test_unknown_module_raises(self):
        with pytest.raises(ValueError, match="unknown module"):
            _resolve_prompt_reference("module:does.not.exist:CONST")

    def test_unknown_attribute_raises(self):
        with pytest.raises(ValueError, match="no attribute"):
            _resolve_prompt_reference(
                "module:strategies.prompts.personas:NOT_A_REAL_CONSTANT"
            )

    def test_non_string_attribute_raises(self):
        # PERSONA_PROMPTS is a dict, not a str
        with pytest.raises(ValueError, match="expected str"):
            _resolve_prompt_reference(
                "module:strategies.prompts.personas:PERSONA_PROMPTS"
            )


# ---------------------------------------------------------------------------
# 4. PERSONA_PROMPTS index
# ---------------------------------------------------------------------------


class TestPersonaPromptsIndex:
    def test_all_six_present(self):
        assert set(PERSONA_PROMPTS) == {
            "buffett_value",
            "graham_deep_value",
            "lynch_growth",
            "munger_quality",
            "klarman_distressed",
            "marks_macro",
        }

    def test_each_prompt_is_substantive(self):
        # Guard against accidentally truncating one
        for name, prompt in PERSONA_PROMPTS.items():
            assert len(prompt) > 200, f"{name} prompt suspiciously short"
            assert prompt.startswith("You are "), f"{name} missing persona opener"

    def test_index_matches_module_constants(self):
        assert PERSONA_PROMPTS["buffett_value"] is BUFFETT_VALUE
        assert PERSONA_PROMPTS["graham_deep_value"] is GRAHAM_DEEP_VALUE
        assert PERSONA_PROMPTS["lynch_growth"] is LYNCH_GROWTH
        assert PERSONA_PROMPTS["munger_quality"] is MUNGER_QUALITY
        assert PERSONA_PROMPTS["klarman_distressed"] is KLARMAN_DISTRESSED
        assert PERSONA_PROMPTS["marks_macro"] is MARKS_MACRO


# ---------------------------------------------------------------------------
# 5. End-to-end: YAML personas load via sentinel and resolve correctly
# ---------------------------------------------------------------------------


class TestPersonasViaYAML:
    def test_paper_yaml_resolves_module_refs(self):
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "agents.paper.yaml"
        agents = load_agents_config(path=str(path))
        by_name = {a.config.name: a for a in agents}

        # Each persona should now hold the FULL resolved prompt, not the
        # "module:..." sentinel.
        expected = {
            "buffett_value": BUFFETT_VALUE,
            "graham_deep_value": GRAHAM_DEEP_VALUE,
            "lynch_growth": LYNCH_GROWTH,
            "munger_quality": MUNGER_QUALITY,
            "klarman_distressed": KLARMAN_DISTRESSED,
            "marks_macro": MARKS_MACRO,
        }

        for name, expected_prompt in expected.items():
            assert name in by_name, f"persona {name!r} missing from YAML load"
            actual = by_name[name].config.system_prompt
            assert actual == expected_prompt, (
                f"{name}: prompt mismatch after resolution.\n"
                f"  Got:  {actual[:80]!r}...\n"
                f"  Want: {expected_prompt[:80]!r}..."
            )
            # Sanity: the sentinel itself must NOT survive into the
            # AgentConfig — it should be replaced.
            assert not actual.startswith("module:"), (
                f"{name}: sentinel leaked through to AgentConfig"
            )
