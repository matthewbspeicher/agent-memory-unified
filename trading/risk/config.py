# risk/config.py
from __future__ import annotations
import yaml
from pydantic import BaseModel, Field, field_validator

from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.rules import (
    MaxComboDelta,
    MaxCorrelation,
    MaxDailyLoss,
    MaxDailyTrades,
    MaxDrawdownPct,
    MaxOpenPositions,
    MaxPortfolioExposure,
    MaxPositionSize,
    RiskRule,
    SectorConcentration,
    MaxPredictionExposure,
)

_RULE_REGISTRY: dict[str, type] = {
    "max_position_size": MaxPositionSize,
    "max_prediction_exposure": MaxPredictionExposure,
    "max_portfolio_exposure": MaxPortfolioExposure,
    "max_daily_loss": MaxDailyLoss,
    "max_open_positions": MaxOpenPositions,
    "max_daily_trades": MaxDailyTrades,
    "sector_concentration": SectorConcentration,
    "max_drawdown_pct": MaxDrawdownPct,
    "max_correlation": MaxCorrelation,
    "max_combo_delta": MaxComboDelta,
}


class RuleConfigSchema(BaseModel):
    type: str
    params: dict = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def type_must_be_known(cls, v: str) -> str:
        if v not in _RULE_REGISTRY:
            raise ValueError(
                f"Unknown rule type '{v}'. Known: {sorted(_RULE_REGISTRY)}"
            )
        return v


class RiskConfigSchema(BaseModel):
    rules: list[RuleConfigSchema] = Field(default_factory=list)
    kill_switch: dict = Field(default_factory=dict)
    external_portfolios: dict = Field(default_factory=dict)


def _build_rule(rule_config: dict) -> RiskRule:
    rule_type = rule_config.get("type")
    cls = _RULE_REGISTRY.get(rule_type)
    if cls is None:
        raise ValueError(
            f"Unknown risk rule: {rule_type}. Known: {list(_RULE_REGISTRY)}"
        )
    params = rule_config.get("params", {})
    return cls(**params)


def load_risk_config(
    path: str,
    leaderboard=None,
    tournament=None,
    perf_store=None,
    agent_store=None,
    settings=None,
    journal_manager=None,
) -> RiskEngine:
    with open(path) as f:
        data = yaml.safe_load(f)

    risk_data = data.get("risk", data)

    from pydantic import ValidationError

    try:
        RiskConfigSchema(**risk_data)
    except ValidationError as exc:
        raise ValueError(f"Invalid risk config '{path}': {exc.errors()}") from exc

    ks = KillSwitch()
    ks_config = risk_data.get("kill_switch", {})
    if isinstance(ks_config, dict) and ks_config.get("enabled", False):
        ks.enable("enabled in config")

    rules = []

    # Prepend CapitalGovernor if dependencies are provided
    governor = None
    if leaderboard and tournament and perf_store and agent_store and settings:
        from risk.governor import CapitalGovernor

        governor = CapitalGovernor(
            leaderboard=leaderboard,
            tournament=tournament,
            perf_store=perf_store,
            agent_store=agent_store,
            settings=settings,
        )
        rules.append(governor)

    # Prepend DejaVuGuard if journal manager is available
    if journal_manager:
        from risk.deja_vu import DejaVuGuard

        rules.append(DejaVuGuard(journal_manager=journal_manager))

    for r in risk_data.get("rules", []):
        if r is None:
            continue
        rules.append(_build_rule(dict(r) if isinstance(r, dict) else r))

    return RiskEngine(rules=rules, kill_switch=ks, governor=governor)
