"""
Rules loader — parses trading_rules.yaml into typed dataclasses.

Watches file mtime and reloads automatically on change.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "trading_rules.yaml"


@dataclass(frozen=True)
class SessionBiasConfig:
    timeframes: list[str] = field(default_factory=lambda: ["1d"])
    indicators: list[str] = field(default_factory=lambda: ["rsi_14", "ema_200", "macd"])
    bullish_criteria: list[str] = field(default_factory=list)
    bearish_criteria: list[str] = field(default_factory=list)
    neutral_criteria: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskOverlay:
    max_new_positions_per_session: int = 3
    avoid_first_30_min: bool = True
    require_bias_alignment: bool = True


@dataclass(frozen=True)
class TradingRules:
    watchlist: dict[str, list[str]] = field(default_factory=dict)
    session_bias: SessionBiasConfig = field(default_factory=SessionBiasConfig)
    risk_overlay: RiskOverlay = field(default_factory=RiskOverlay)

    @property
    def all_symbols(self) -> list[str]:
        """Flatten all watchlist groups into a single list."""
        symbols = []
        for group in self.watchlist.values():
            symbols.extend(group)
        return symbols


class RulesLoader:
    """Loads and caches TradingRules from YAML, auto-reloading on file change."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_RULES_PATH
        self._rules: TradingRules | None = None
        self._mtime: float = 0.0

    def get(self) -> TradingRules:
        """Return current rules, reloading if file changed."""
        try:
            current_mtime = os.path.getmtime(self._path)
        except OSError:
            logger.warning("Trading rules file not found: %s", self._path)
            if self._rules:
                return self._rules
            return TradingRules()

        if self._rules is None or current_mtime > self._mtime:
            self._rules = self._load()
            self._mtime = current_mtime
        return self._rules

    def _load(self) -> TradingRules:
        try:
            with open(self._path) as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to load trading rules from %s: %s", self._path, e)
            return TradingRules()

        watchlist = data.get("watchlist", {})
        bias_data = data.get("session_bias", {})
        risk_data = data.get("risk_overlay", {})

        session_bias = SessionBiasConfig(
            timeframes=bias_data.get("timeframes", ["1d"]),
            indicators=bias_data.get("indicators", []),
            bullish_criteria=bias_data.get("bullish_criteria", []),
            bearish_criteria=bias_data.get("bearish_criteria", []),
            neutral_criteria=bias_data.get("neutral_criteria", []),
        )

        risk_overlay = RiskOverlay(
            max_new_positions_per_session=risk_data.get("max_new_positions_per_session", 3),
            avoid_first_30_min=risk_data.get("avoid_first_30_min", True),
            require_bias_alignment=risk_data.get("require_bias_alignment", True),
        )

        logger.info(
            "Loaded trading rules: %d symbols across %d watchlist groups",
            sum(len(v) for v in watchlist.values()),
            len(watchlist),
        )

        return TradingRules(
            watchlist=watchlist,
            session_bias=session_bias,
            risk_overlay=risk_overlay,
        )
