"""Prompts for TradeReflector deep reflection.

Portions adapted from TradingAgents by TauricResearch
https://github.com/TauricResearch/TradingAgents
Licensed under Apache License 2.0.
"""

from __future__ import annotations


REFLECTION_SYSTEM = """You review closed trades to produce one short,
falsifiable lesson the agent should carry forward.

A good lesson is:
- specific: names the feature (a level, a regime, a sentiment signal), not
  "the market"
- falsifiable: makes a prediction a future scan could verify
- calibrated: if the trade lost because confidence was overestimated, says so
- portable: useful across multiple future trades of this agent

A bad lesson is:
- hindsight ("should have exited earlier")
- vague ("be more careful with volatility")
- generic ("watch the news")

A win driven by luck (large positive surprise_ratio) is NOT evidence the
entry reasoning was right. Flag it so the agent doesn't over-update.

Return strict JSON. Do not include prose outside the JSON.
"""


REFLECTION_USER_TEMPLATE = """Closed trade
-------------
agent:          {agent_name}
symbol:         {symbol}
direction:      {direction}
entry_price:    {entry_price}
exit_price:     {exit_price}
realized_pnl:   {pnl}
expected_pnl:   {expected_pnl}
surprise_ratio: {surprise_ratio}      (|realized - expected| / max(|expected|, 1))
outcome:        {outcome}
signal_strength:{signal_strength}
hold_minutes:   {hold_minutes}
slippage_bps:   {slippage_bps}
regime:         {regime}

Task
----
1. Identify the single biggest belief at entry that turned out wrong (or
   right for the wrong reason). Quote or paraphrase it.
2. State the one feature of the market context the agent should weigh more
   heavily next time.
3. Write a one-sentence lesson starting with "When X, prefer Y."
4. Assign exactly one category: calibration | regime | feature | risk | timing.
5. Write a factual, reusable market observation if one emerged — otherwise
   empty string.

Return strict JSON matching the reflection_lesson schema.
"""


REFLECTION_SCHEMA: dict = {
    "name": "reflection_lesson",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["belief", "feature", "lesson", "category"],
        "properties": {
            "belief": {"type": "string", "maxLength": 400},
            "feature": {"type": "string", "maxLength": 200},
            "lesson": {"type": "string", "maxLength": 300},
            "category": {
                "enum": ["calibration", "regime", "feature", "risk", "timing"],
            },
            "market_observation": {"type": "string", "maxLength": 300},
        },
    },
}
