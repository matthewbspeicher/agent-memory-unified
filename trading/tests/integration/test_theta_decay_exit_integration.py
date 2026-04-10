"""Integration tests for Theta Decay Exit Rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from broker.models import AssetType
from exits.manager import ExitManager
from exits.rules import ThetaDecayExit


class TestThetaDecayExitIntegration:
    """Integration tests for theta decay exit rules."""

    @pytest.mark.asyncio
    async def test_theta_exit_added_for_prediction_markets(self):
        """Test that ThetaDecayExit is added for prediction market positions."""
        manager = ExitManager()

        rules = manager.compute_default_exits(
            side="BUY",
            entry_price=Decimal("0.50"),
            asset_type=AssetType.PREDICTION,
            contract_expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        )

        rule_types = [type(r).__name__ for r in rules]
        assert "ThetaDecayExit" in rule_types

    @pytest.mark.asyncio
    async def test_theta_exit_not_added_for_stocks(self):
        """Test that ThetaDecayExit is not added for stock positions."""
        manager = ExitManager()

        rules = manager.compute_default_exits(
            side="BUY",
            entry_price=Decimal("450.00"),
            asset_type=AssetType.STOCK,
        )

        rule_types = [type(r).__name__ for r in rules]
        assert "ThetaDecayExit" not in rule_types

    @pytest.mark.asyncio
    async def test_theta_exit_triggers_on_profit(self):
        """Test that theta exit triggers when profit target is reached."""
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,  # 50% profit
            stop_loss_pct=2.0,
            side="BUY",
        )

        # 50% profit: 0.50 -> 0.75
        assert rule.should_exit(Decimal("0.75")) is True

    @pytest.mark.asyncio
    async def test_theta_exit_triggers_on_dte_threshold(self):
        """Test that theta exit triggers when DTE falls below minimum."""
        expires = datetime.now(timezone.utc) + timedelta(days=1)
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            min_dte=2,
            expires_at=expires,
            side="BUY",
        )

        # 1 day remaining, min_dte=2 -> should exit
        assert rule.should_exit(Decimal("0.52")) is True

    @pytest.mark.asyncio
    async def test_theta_exit_sell_side_profit_calculation(self):
        """Test that theta exit correctly handles SELL profit."""
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            side="SELL",
        )

        # SELL at 0.50, price drops to 0.25 = 50% profit
        assert rule.should_exit(Decimal("0.25")) is True

    @pytest.mark.asyncio
    async def test_theta_exit_sell_side_stop_loss(self):
        """Test that theta exit correctly handles SELL stop loss."""
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,  # 200% stop loss
            side="SELL",
        )

        # SELL at 0.50, price rises to 1.50 = 200% loss (stop loss)
        assert rule.should_exit(Decimal("1.50")) is True
