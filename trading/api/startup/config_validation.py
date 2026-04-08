"""Fail-fast config validation (before DB init or broker connect)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config import Config
    from learning.config import LearningConfig
    from utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


@dataclass
class ValidatedConfigs:
    """Container for all validated configuration artifacts needed downstream."""

    learning_cfg: LearningConfig
    learning_data: dict[str, Any] | None
    risk_path_str: str | None
    risk_data: dict[str, Any] | None
    agents_data: dict[str, Any] | None
    agents_path_str: str | None


async def validate_configs(
    config: Config, config_loader: ConfigLoader
) -> ValidatedConfigs:
    """Validate risk, agents, and learning YAML configs using Pydantic schemas.

    Raises ``ValidationError`` or ``Exception`` on any config error so the
    application fails fast before connecting to databases or brokers.
    """
    from pydantic import ValidationError
    from risk.config import RiskConfigSchema
    from agents.config import AgentsFileSchema, _ensure_strategies_registered
    from learning.config import LearningConfig, MemoryConfig, StrategyHealthConfig

    try:
        # 1. Resolve and load Risk Config
        risk_path_str = config_loader.resolve("risk.yaml")
        risk_data = config_loader.load_yaml("risk.yaml")

        if risk_data:
            RiskConfigSchema(**risk_data.get("risk", risk_data))
        else:
            logger.warning(
                "Config validation: risk.yaml not found, skipping validation"
            )

        # 2. Resolve and load Agents Config
        if config.agents_config:
            agents_yaml_name = config.agents_config
        elif config.paper_trading:
            agents_yaml_name = "agents.paper.yaml"
        else:
            agents_yaml_name = "agents.yaml"

        agents_path_str = config_loader.resolve(agents_yaml_name)
        agents_data = config_loader.load_yaml(agents_yaml_name)

        if agents_data:
            _ensure_strategies_registered()
            AgentsFileSchema(agents=agents_data.get("agents", []))
        else:
            logger.warning(
                "Config validation: agents config not found, skipping validation"
            )

        # 3. Resolve and load Learning Config
        _learning_path_str = config_loader.resolve("learning.yaml")
        learning_data = config_loader.load_yaml("learning.yaml")

        if learning_data:
            learning_cfg = LearningConfig(**learning_data)
        else:
            logger.warning(
                "Config validation: learning.yaml not found, using empty config"
            )
            learning_cfg = LearningConfig(
                memory=MemoryConfig(enabled=False),
                strategy_health=StrategyHealthConfig(enabled=False)
            )
    except ValidationError as exc:
        logger.critical("Config validation failed: %s", exc.errors())
        raise
    except Exception as exc:
        logger.critical("Config file error: %s", exc)
        raise

    return ValidatedConfigs(
        learning_cfg=learning_cfg,
        learning_data=learning_data,
        risk_path_str=risk_path_str,
        risk_data=risk_data,
        agents_data=agents_data,
        agents_path_str=agents_path_str,
    )
