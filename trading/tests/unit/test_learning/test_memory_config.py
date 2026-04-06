import yaml
from learning.config import LearningConfig


def test_learning_config_with_memory_section():
    raw = yaml.safe_load("""
pnl:
  mark_to_market_seconds: 60
  reconciliation_seconds: 300
retention:
  default_days: 90
optimization:
  min_backtest_trades: 30
  min_paper_days: 7
  tournament_challengers: 4
  tournament_promotion_margin: 0.10
  grid_search_schedule: "0 2 * * 0"
reflection:
  feedback_model: "claude-sonnet-4-20250514"
  synthesis_model: "claude-sonnet-4-20250514"
  synthesis_interval_days: 7
  max_learned_rules: 10
  recent_lessons_window: 5
  auto_revert_sharpe_drop: 0.20
guardrails:
  max_daily_parameter_changes: 1
  max_parameter_change_pct: 0.20
  cooldown_after_disable_hours: 48
memory:
  enabled: true
  deep_reflection:
    pnl_multiplier: 2.0
    loss_multiplier: 1.5
  ttl_days: 90
  pre_trade_query:
    enabled: true
    top_k: 5
""")
    config = LearningConfig(**raw)
    assert config.memory.enabled is True
    assert config.memory.deep_reflection.pnl_multiplier == 2.0
    assert config.memory.ttl_days == 90
    assert config.memory.pre_trade_query.top_k == 5


def test_learning_config_memory_defaults_to_disabled():
    """Existing learning.yaml without memory: section stays valid — memory disabled."""
    raw = yaml.safe_load("""
pnl:
  mark_to_market_seconds: 60
  reconciliation_seconds: 300
retention:
  default_days: 90
optimization:
  min_backtest_trades: 30
  min_paper_days: 7
  tournament_challengers: 4
  tournament_promotion_margin: 0.10
  grid_search_schedule: "0 2 * * 0"
reflection:
  feedback_model: "claude-sonnet-4-20250514"
  synthesis_model: "claude-sonnet-4-20250514"
  synthesis_interval_days: 7
  max_learned_rules: 10
  recent_lessons_window: 5
  auto_revert_sharpe_drop: 0.20
guardrails:
  max_daily_parameter_changes: 1
  max_parameter_change_pct: 0.20
  cooldown_after_disable_hours: 48
""")
    config = LearningConfig(**raw)
    assert config.memory.enabled is False
