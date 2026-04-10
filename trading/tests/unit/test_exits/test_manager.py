"""Tests for ExitManager with persistence."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from exits.manager import ExitManager
from exits.rules import StopLoss, TakeProfit, TrailingStop


class TestExitManager:
    @pytest.mark.asyncio
    async def test_attach_persists_to_store(self):
        store = MagicMock()
        store.save = AsyncMock()
        manager = ExitManager(store=store)

        rules = [
            StopLoss(stop_price=Decimal("90")),
            TakeProfit(target_price=Decimal("120")),
        ]
        await manager.attach(position_id=1, rules=rules)

        store.save.assert_awaited_once()
        assert manager.check(position_id=1, current_price=Decimal("100")) is None

    @pytest.mark.asyncio
    async def test_detach_removes_from_store(self):
        store = MagicMock()
        store.save = AsyncMock()
        store.delete = AsyncMock()
        manager = ExitManager(store=store)

        await manager.attach(position_id=1, rules=[StopLoss(stop_price=Decimal("90"))])
        await manager.detach(position_id=1)

        store.delete.assert_awaited_once_with(1)
        assert manager.check(position_id=1, current_price=Decimal("50")) is None

    @pytest.mark.asyncio
    async def test_load_rules_restores_persisted_rules(self):
        store = MagicMock()
        store.load_all = AsyncMock(
            return_value={
                7: [{"type": "stop_loss", "stop_price": "95", "side": "BUY"}],
            }
        )
        manager = ExitManager(store=store)

        await manager.load_rules()

        result = manager.check(position_id=7, current_price=Decimal("94"))
        assert result is not None
        assert result.name == "stop_loss"

    def test_stop_loss_triggers(self):
        manager = ExitManager(store=MagicMock())
        manager._rules[1] = [
            StopLoss(stop_price=Decimal("95")),
            TakeProfit(target_price=Decimal("120")),
        ]
        result = manager.check(position_id=1, current_price=Decimal("94"))
        assert result is not None
        assert result.name == "stop_loss"

    def test_trailing_stop_tracks_peak(self):
        manager = ExitManager(store=MagicMock())
        trail = TrailingStop(trail_pct=Decimal("0.05"))
        manager._rules[1] = [trail]
        manager.update_trailing(position_id=1, current_price=Decimal("100"))
        manager.update_trailing(position_id=1, current_price=Decimal("110"))
        assert manager.check(position_id=1, current_price=Decimal("106")) is None
        assert manager.check(position_id=1, current_price=Decimal("104")) is not None

    def test_check_no_rules_returns_none(self):
        manager = ExitManager(store=MagicMock())
        result = manager.check(position_id=999, current_price=Decimal("100"))
        assert result is None

    def test_take_profit_triggers(self):
        manager = ExitManager(store=MagicMock())
        manager._rules[2] = [TakeProfit(target_price=Decimal("120"), side="BUY")]
        result = manager.check(position_id=2, current_price=Decimal("125"))
        assert result is not None
        assert result.name == "take_profit"

    @pytest.mark.asyncio
    async def test_attach_without_store_works(self):
        manager = ExitManager(store=None)
        rules = [StopLoss(stop_price=Decimal("90"))]
        await manager.attach(position_id=1, rules=rules)
        assert manager.check(position_id=1, current_price=Decimal("89")) is not None

    def test_compute_default_exits_buy(self):
        manager = ExitManager(store=None)
        exits = manager.compute_default_exits(side="BUY", entry_price=Decimal("100"))
        names = [r.name for r in exits]
        assert "stop_loss" in names
        assert "take_profit" in names
        assert "trailing_stop" in names

    def test_compute_default_exits_sell(self):
        manager = ExitManager(store=None)
        exits = manager.compute_default_exits(side="SELL", entry_price=Decimal("100"))
        names = [r.name for r in exits]
        assert "stop_loss" in names
        assert "take_profit" in names


# ---------------------------------------------------------------------------
# Prediction-market-specific defaults
# ---------------------------------------------------------------------------


class TestComputeDefaultExitsPrediction:
    def _em(self):
        from exits.manager import ExitManager

        return ExitManager()

    def test_prediction_without_expiry_returns_trailing_only(self):
        from broker.models import AssetType
        from decimal import Decimal

        em = self._em()
        rules = em.compute_default_exits(
            "BUY", Decimal("0.60"), asset_type=AssetType.PREDICTION
        )
        from exits.rules import ProbabilityTrailingStop

        assert len(rules) == 1
        assert isinstance(rules[0], ProbabilityTrailingStop)

    def test_prediction_with_expiry_returns_theta_pre_expiry_and_trailing(self):
        from broker.models import AssetType
        from decimal import Decimal
        from datetime import datetime, timezone, timedelta
        from exits.rules import PreExpiryExit, ProbabilityTrailingStop, ThetaDecayExit

        em = self._em()
        expiry = datetime.now(timezone.utc) + timedelta(hours=10)
        rules = em.compute_default_exits(
            "BUY",
            Decimal("0.60"),
            asset_type=AssetType.PREDICTION,
            contract_expires_at=expiry,
        )
        assert len(rules) == 3
        assert isinstance(rules[0], ThetaDecayExit)
        assert isinstance(rules[1], PreExpiryExit)
        assert isinstance(rules[2], ProbabilityTrailingStop)

    def test_equity_defaults_unchanged(self):
        from decimal import Decimal
        from exits.rules import StopLoss, TakeProfit, TrailingStop

        em = self._em()
        rules = em.compute_default_exits("BUY", Decimal("100.00"))
        assert len(rules) == 3
        assert isinstance(rules[0], StopLoss)
        assert isinstance(rules[1], TakeProfit)
        assert isinstance(rules[2], TrailingStop)

    @pytest.mark.asyncio
    async def test_update_trailing_calls_probability_trailing_stop(self):
        from decimal import Decimal
        from exits.rules import ProbabilityTrailingStop

        em = self._em()
        rule = ProbabilityTrailingStop(trail_pp=15.0)
        await em.attach(42, [rule])
        em.update_trailing(42, Decimal("0.75"))
        assert rule._peak == 0.75

    @pytest.mark.asyncio
    async def test_check_passes_current_time_to_pre_expiry(self):
        from decimal import Decimal
        from datetime import datetime, timezone, timedelta
        from exits.rules import PreExpiryExit

        em = self._em()
        expires = datetime.now(timezone.utc) + timedelta(hours=2)
        rule = PreExpiryExit(expires_at=expires, hours_before_expiry=4.0)
        await em.attach(99, [rule])
        result = em.check(99, Decimal("0.60"))
        assert result is rule  # 2h remaining < 4h window → trigger
