from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field
from typing import Literal


class BiasCriteria(BaseModel):
    bullish: list[str]
    bearish: list[str]


class StrategyConfig(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0"
    sources: list[str] = Field(default_factory=list)


class IndicatorsConfig(BaseModel):
    pass


class RiskRule(BaseModel):
    rule: str
    params: dict[str, object] = Field(default_factory=dict)


class StrategyFile(BaseModel):
    watchlist: list[str] = Field(default_factory=list)
    default_timeframe: str = "1h"
    strategy: StrategyConfig
    indicators: IndicatorsConfig = Field(default_factory=IndicatorsConfig)
    bias_criteria: BiasCriteria = BiasCriteria(bullish=[], bearish=[])
    entry_rules: dict[Literal["long", "short"], list[str]] = Field(default_factory=dict)
    exit_rules: list[str] = Field(default_factory=list)
    risk_rules: list[str] = Field(default_factory=list)
    notes: str = ""
