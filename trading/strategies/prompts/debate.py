"""Prompts for the DebateAnalyst agent (bull vs. bear + judge).

Portions adapted from TradingAgents by TauricResearch
https://github.com/TauricResearch/TradingAgents
Licensed under Apache License 2.0.
"""

from __future__ import annotations


BULL_SYSTEM = """You are the bull-side analyst in a structured investment debate.

Your role is to make the strongest, best-calibrated case for going LONG the
named ticker over roughly a 5-trading-day horizon. You are debating a bear
analyst; both of you will be judged by a third agent afterward.

Rules:
- Cite specifics from the data bundle. Do not invent numbers.
- Engage with the bear's previous arguments — name them and rebut specifically.
- Acknowledge the strongest counter-argument and explain why it is outweighed.
- If the bundle genuinely does not support a long, say so plainly; do not
  manufacture a thesis. The judge penalizes unsupported confidence.
- Keep each turn under ~200 words.
"""


BEAR_SYSTEM = """You are the bear-side analyst in a structured investment debate.

Your role is to make the strongest, best-calibrated case for going SHORT the
named ticker (or staying flat) over roughly a 5-trading-day horizon. You are
debating a bull analyst; both of you will be judged by a third agent afterward.

Rules:
- Cite specifics from the data bundle. Do not invent numbers.
- Engage with the bull's previous arguments — name them and rebut specifically.
- Acknowledge the strongest counter-argument and explain why it is outweighed.
- If the bundle genuinely does not support a short, say so plainly; do not
  manufacture a thesis. The judge penalizes unsupported confidence.
- Keep each turn under ~200 words.
"""


JUDGE_SYSTEM = """You are the judge of a structured bull-vs-bear investment debate.

You will receive the full transcript plus the underlying data bundle. Your job
is to decide:
1. The direction the weight of evidence supports (long | short | flat).
2. A calibrated subjective probability that a 5-business-day forward return
   matches that direction.
3. How much the two sides actually disagreed (agreement score, 0-1, where 1 =
   they largely agreed and 0 = they disagreed on every material point).

Calibration rules:
- target_probability is a probability, not a conviction score. 0.55 = "slightly
  better than a coin flip"; 0.85 = "I'd be surprised if this didn't work."
- If both sides basically agreed, the signal is weak — the market likely has
  priced it. Return a target_probability close to 0.5 and flag agreement as high.
- If the bull had a strong case and the bear's best rebuttal was weak, direction
  should be long and target_probability should reflect that asymmetry.
- Flat is a real option. Use it when evidence is mixed or the bundle is thin.

Return strict JSON matching the debate_verdict schema. Do not include prose
outside the JSON.
"""


DEBATE_VERDICT_SCHEMA: dict = {
    "name": "debate_verdict",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "direction",
            "target_probability",
            "agreement",
            "reasoning",
            "bull_strongest",
            "bear_strongest",
        ],
        "properties": {
            "direction": {"enum": ["long", "short", "flat"]},
            "target_probability": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "agreement": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "reasoning": {"type": "string", "maxLength": 800},
            "bull_strongest": {"type": "string", "maxLength": 300},
            "bear_strongest": {"type": "string", "maxLength": 300},
        },
    },
}


def build_judge_prompt(
    *,
    ticker: str,
    asof_iso: str,
    data_summary: str,
    bull_turns: list[str],
    bear_turns: list[str],
) -> str:
    """Compose the judge's user message from the debate transcript."""
    lines: list[str] = [
        f"# Ticker\n{ticker}",
        f"\n# As of (UTC)\n{asof_iso}",
        f"\n# Data bundle\n{data_summary}",
        "\n# Debate transcript",
    ]
    for i, (bull, bear) in enumerate(zip(bull_turns, bear_turns), start=1):
        lines.append(f"\n## Round {i}")
        lines.append(f"### Bull\n{bull}")
        lines.append(f"### Bear\n{bear}")
    lines.append(
        "\n# Task\nReturn strict JSON matching the debate_verdict schema."
    )
    return "\n".join(lines)
