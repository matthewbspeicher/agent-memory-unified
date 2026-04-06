from learning.config import load_learning_config


class TestLearningConfig:
    def test_load_learning_config_from_dict(self):
        """Test loading config with specific values."""
        data = {
            "pnl": {
                "mark_to_market_seconds": 120,
                "reconciliation_seconds": 600,
            },
            "retention": {
                "default_days": 180,
                "per_agent": {
                    "agent-1": 365,
                    "agent-2": 30,
                },
            },
            "optimization": {
                "min_backtest_trades": 50,
                "min_paper_days": 14,
                "tournament_challengers": 8,
                "tournament_promotion_margin": 0.15,
                "grid_search_schedule": "0 3 * * 1",
            },
            "guardrails": {
                "max_daily_parameter_changes": 2,
                "max_parameter_change_pct": 0.25,
                "cooldown_after_disable_hours": 72,
            },
            "reflection": {
                "feedback_model": "claude-opus-4-1",
                "synthesis_model": "claude-opus-4-1",
                "synthesis_interval_days": 14,
                "max_learned_rules": 20,
                "recent_lessons_window": 10,
                "auto_revert_sharpe_drop": 0.30,
            },
            "triggers": {
                "high_drawdown": 0.10,
                "low_sharpe": 0.5,
            },
        }

        config = load_learning_config(data)

        # Assert nested pnl values
        assert config.pnl.mark_to_market_seconds == 120
        assert config.pnl.reconciliation_seconds == 600

        # Assert nested retention values
        assert config.retention.default_days == 180
        assert config.retention.per_agent == {
            "agent-1": 365,
            "agent-2": 30,
        }

        # Assert nested optimization values
        assert config.optimization.min_backtest_trades == 50
        assert config.optimization.min_paper_days == 14
        assert config.optimization.tournament_challengers == 8
        assert config.optimization.tournament_promotion_margin == 0.15
        assert config.optimization.grid_search_schedule == "0 3 * * 1"

        # Assert nested guardrails values
        assert config.guardrails.cooldown_after_disable_hours == 72
        assert config.guardrails.max_daily_parameter_changes == 2
        assert config.guardrails.max_parameter_change_pct == 0.25

        # Assert nested reflection values
        assert config.reflection.feedback_model == "claude-opus-4-1"
        assert config.reflection.synthesis_model == "claude-opus-4-1"
        assert config.reflection.synthesis_interval_days == 14
        assert config.reflection.max_learned_rules == 20
        assert config.reflection.recent_lessons_window == 10
        assert config.reflection.auto_revert_sharpe_drop == 0.30

        # Assert triggers
        assert config.triggers == {
            "high_drawdown": 0.10,
            "low_sharpe": 0.5,
        }

    def test_load_learning_config_defaults(self):
        """Test loading config with empty dict uses all defaults."""
        config = load_learning_config({})

        # Assert all defaults via nested models
        assert config.pnl.mark_to_market_seconds == 60
        assert config.pnl.reconciliation_seconds == 300
        assert config.retention.default_days == 90
        assert config.retention.per_agent == {}
        assert config.optimization.min_backtest_trades == 30
        assert config.optimization.min_paper_days == 7
        assert config.optimization.tournament_challengers == 4
        assert config.optimization.tournament_promotion_margin == 0.10
        assert config.optimization.grid_search_schedule == "0 2 * * 0"
        assert config.guardrails.max_daily_parameter_changes == 1
        assert config.guardrails.max_parameter_change_pct == 0.20
        assert config.guardrails.cooldown_after_disable_hours == 48
        assert config.reflection.feedback_model == "claude-sonnet-4-20250514"
        assert config.reflection.synthesis_model == "claude-sonnet-4-20250514"
        assert config.reflection.synthesis_interval_days == 7
        assert config.reflection.max_learned_rules == 10
        assert config.reflection.recent_lessons_window == 5
        assert config.reflection.auto_revert_sharpe_drop == 0.20
        assert config.triggers == {}
