from __future__ import annotations

from pydantic import BaseModel
from typing import Literal


class BiasCriteria(BaseModel):
    bullish: list[str]
    bearish: list[str]


class StrategyConfig(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0"
    sources: list[str] = []


class IndicatorsConfig(BaseModel):
    pass


class RiskRule(BaseModel):
    rule: str
    params: dict = {}


class StrategyFile(BaseModel):
    watchlist: list[str] = []
    default_timeframe: str = "1h"
    strategy: StrategyConfig
    indicators: IndicatorsConfig = {}
    bias_criteria: BiasCriteria = BiasCriteria(bullish=[], bearish=[])
    entry_rules: dict[Literal["long", "short"], list[str]] = {}
    exit_rules: list[str] = []
    risk_rules: list[str] = []
    notes: str = ""
