"""Prompts and schemas for the PersonaPanelAgent.

Where ``debate.py`` runs an adversarial bull-vs-bear back-and-forth, the
panel pipeline collects ONE independent opinion per persona (Buffett,
Graham, …) and feeds them to a judge for synthesis.  No multi-round
engagement — panelists never see each other's reasoning until the judge
sees all of them at once.

Persona system prompts live in ``personas.py`` and are reused unchanged.
The schema for an individual panelist's opinion reuses
``analysts.ANALYST_SCHEMA``.

Verdict schema mirrors ``debate.DEBATE_VERDICT_SCHEMA`` (same fields:
direction, target_probability, agreement, reasoning) so downstream
``_to_opportunity`` logic in ``persona_panel.py`` matches
``debate_analyst.py`` exactly.
"""

from __future__ import annotations


PANEL_JUDGE_SYSTEM = """You are the judge of a panel of named investor personas.

You will receive a data bundle plus one independent opinion from each
panelist (Buffett, Graham, Lynch, Munger, Klarman, Marks — or a subset).
Each panelist returned: direction (long|short|flat), their own confidence,
short reasoning, and key risks.

Your job is to synthesize them into:
1. direction (long | short | flat)
2. target_probability — calibrated subjective probability that a
   5-business-day forward return matches that direction
3. agreement (0-1) — how unanimous the panel was. 1 = everyone agrees,
   0 = full disagreement.
4. reasoning — concise synthesis citing the panelists by name

Calibration rules:
- Treat panelists' own confidence numbers as priors, not facts. A persona
  can be confidently wrong; calibrate against the data bundle.
- Disagreement is informative, not noise. A 6-0 unanimous panel suggests
  the call is obvious — and therefore likely already priced. A 4-2 split
  with a strong minority is often a stronger signal than unanimity.
- A persona explicitly disqualifying themselves (e.g. Graham passing on a
  growth stock with no asset backing) is NOT a vote. Weight it as such.
- Flat is a real verdict. Use it when the panel is genuinely split or the
  bundle is too thin.

Output strict JSON matching the panel_verdict schema. Do not include prose
outside the JSON.
"""


PANEL_VERDICT_SCHEMA: dict = {
    "name": "panel_verdict",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "direction",
            "target_probability",
            "agreement",
            "reasoning",
            "majority_personas",
            "dissenting_personas",
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
            "majority_personas": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
            },
            "dissenting_personas": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
            },
        },
    },
}


def build_panelist_user_message(
    *,
    ticker: str,
    asof_iso: str,
    data_summary: str,
) -> str:
    """User message that pairs with a persona system prompt."""
    return (
        f"# Ticker\n{ticker}\n\n"
        f"# As of (UTC)\n{asof_iso}\n\n"
        f"# Data bundle\n{data_summary}\n\n"
        "Apply your investment lens to this data. Return strict JSON with "
        "fields: signal (long|short|flat), confidence (0-1), reasoning "
        "(<400 chars), key_risks (array, up to 3). If your lens does not "
        "apply to this asset class, return signal='flat' with low "
        "confidence and explain in reasoning."
    )


def build_panel_judge_prompt(
    *,
    ticker: str,
    asof_iso: str,
    data_summary: str,
    opinions: list[dict],
) -> str:
    """Compose the judge's user message from N panelist opinions.

    Each opinion dict carries:
        persona: str            (e.g. "buffett_value")
        signal: str             (long|short|flat)
        confidence: float       (0-1, as the persona reported)
        reasoning: str
        key_risks: list[str]    (may be empty)
    """
    lines: list[str] = [
        f"# Ticker\n{ticker}",
        f"\n# As of (UTC)\n{asof_iso}",
        f"\n# Data bundle\n{data_summary}",
        "\n# Panel opinions",
    ]
    for op in opinions:
        risks = op.get("key_risks") or []
        risks_str = "; ".join(risks) if risks else "(none)"
        lines.append(
            f"\n## {op.get('persona', 'unknown')}\n"
            f"- signal: {op.get('signal', '?')}\n"
            f"- confidence: {op.get('confidence', 0):.2f}\n"
            f"- reasoning: {op.get('reasoning', '').strip()}\n"
            f"- key risks: {risks_str}"
        )
    lines.append(
        "\n# Task\nSynthesize the panel into one verdict. Return strict JSON "
        "matching the panel_verdict schema. Cite panelists by name in "
        "majority_personas and dissenting_personas."
    )
    return "\n".join(lines)
