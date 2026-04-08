"""Tests for the trading rules loader (brief/rules_loader.py)."""

import tempfile
from pathlib import Path

import pytest
import yaml

from brief.rules_loader import RulesLoader, TradingRules, SessionBiasConfig, RiskOverlay


@pytest.fixture
def rules_yaml(tmp_path: Path) -> Path:
    data = {
        "watchlist": {
            "crypto": ["BTCUSD", "ETHUSD"],
            "indices": ["SPY"],
        },
        "session_bias": {
            "timeframes": ["1d", "4h"],
            "indicators": ["rsi_14", "ema_200"],
            "bullish_criteria": ["price above EMA 200"],
            "bearish_criteria": ["price below EMA 200"],
            "neutral_criteria": ["no clear trend"],
        },
        "risk_overlay": {
            "max_new_positions_per_session": 5,
            "avoid_first_30_min": False,
            "require_bias_alignment": True,
        },
    }
    path = tmp_path / "trading_rules.yaml"
    path.write_text(yaml.dump(data))
    return path


def test_loads_valid_yaml(rules_yaml: Path):
    loader = RulesLoader(rules_yaml)
    rules = loader.get()

    assert isinstance(rules, TradingRules)
    assert rules.watchlist["crypto"] == ["BTCUSD", "ETHUSD"]
    assert rules.watchlist["indices"] == ["SPY"]
    assert rules.all_symbols == ["BTCUSD", "ETHUSD", "SPY"]


def test_session_bias_config(rules_yaml: Path):
    rules = RulesLoader(rules_yaml).get()

    assert rules.session_bias.timeframes == ["1d", "4h"]
    assert "rsi_14" in rules.session_bias.indicators
    assert len(rules.session_bias.bullish_criteria) == 1


def test_risk_overlay(rules_yaml: Path):
    rules = RulesLoader(rules_yaml).get()

    assert rules.risk_overlay.max_new_positions_per_session == 5
    assert rules.risk_overlay.avoid_first_30_min is False
    assert rules.risk_overlay.require_bias_alignment is True


def test_missing_file_returns_defaults():
    loader = RulesLoader("/nonexistent/path.yaml")
    rules = loader.get()

    assert isinstance(rules, TradingRules)
    assert rules.watchlist == {}
    assert rules.all_symbols == []


def test_caches_and_reloads_on_change(rules_yaml: Path):
    loader = RulesLoader(rules_yaml)
    rules1 = loader.get()
    rules2 = loader.get()
    assert rules1 is rules2  # same object (cached)

    # Modify file
    import time
    time.sleep(0.1)  # ensure mtime changes
    data = yaml.safe_load(rules_yaml.read_text())
    data["watchlist"]["crypto"].append("SOLUSD")
    rules_yaml.write_text(yaml.dump(data))

    rules3 = loader.get()
    assert "SOLUSD" in rules3.all_symbols


def test_empty_yaml_returns_defaults(tmp_path: Path):
    path = tmp_path / "empty.yaml"
    path.write_text("")

    rules = RulesLoader(path).get()
    assert isinstance(rules, TradingRules)
    assert rules.all_symbols == []
