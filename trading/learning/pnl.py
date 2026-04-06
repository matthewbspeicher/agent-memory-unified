from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from storage.pnl import TrackedPositionStore

if TYPE_CHECKING:
    from agents.models import Opportunity
    from broker.models import OrderResult
    from data.bus import DataBus
    from learning.confidence_calibration import ConfidenceCalibrationConfig
    from storage.confidence_calibration import ConfidenceCalibrationStore
    from storage.signal_features import SignalFeatureStore
    from storage.trade_analytics import TradeAnalyticsStore

_log = logging.getLogger(__name__)


class TradeTracker:
    def __init__(
        self,
        store: TrackedPositionStore,
        data_bus: DataBus | None = None,
        analytics_store: TradeAnalyticsStore | None = None,
        opportunity_store=None,
        execution_quality_store=None,
        signal_feature_store: SignalFeatureStore | None = None,
        confidence_calibration_store: ConfidenceCalibrationStore | None = None,
        confidence_calibration_config: ConfidenceCalibrationConfig | None = None,
    ) -> None:
        self._store = store
        self._data_bus = data_bus
        self._analytics_store = analytics_store
        self._opportunity_store = opportunity_store
        self._execution_quality_store = execution_quality_store
        self._signal_feature_store = signal_feature_store
        self._confidence_calibration_store = confidence_calibration_store
        self._confidence_calibration_config = confidence_calibration_config

    async def record_entry(
        self, opportunity: Opportunity, order_result: OrderResult, side: str
    ) -> int:
        entry_price = order_result.avg_fill_price or Decimal("0")
        entry_time = order_result.filled_at or datetime.now(timezone.utc)
        return await self._store.open_position(
            agent_name=opportunity.agent_name,
            opportunity_id=opportunity.id,
            symbol=opportunity.symbol.ticker,
            side=side,
            entry_price=str(entry_price),
            entry_quantity=int(order_result.filled_quantity),
            entry_fees=str(order_result.commission),
            entry_time=entry_time.isoformat(),
            broker_id=opportunity.broker_id,
            account_id=getattr(opportunity.suggested_trade, "account_id", None),
        )

    async def record_exit(
        self, position_id: int, order_result: OrderResult, reason: str
    ) -> None:
        exit_price = order_result.avg_fill_price or Decimal("0")
        exit_time = order_result.filled_at or datetime.now(timezone.utc)
        await self._store.close_position(
            position_id,
            exit_price=str(exit_price),
            exit_fees=str(order_result.commission),
            exit_time=exit_time.isoformat(),
            exit_reason=reason,
        )
        if self._analytics_store is not None:
            asyncio.create_task(self._derive_analytics(position_id))

    async def _derive_analytics(self, position_id: int) -> None:
        """Fire-and-forget analytics derivation. Failures are logged, never propagated."""
        try:
            from analytics.strategy_scorecard import derive_and_upsert_for_position

            await derive_and_upsert_for_position(
                position_id,
                self._store,
                self._analytics_store,
                self._opportunity_store,
                self._execution_quality_store,
                self._signal_feature_store,
            )
            if (
                self._analytics_store is not None
                and self._confidence_calibration_store is not None
                and self._confidence_calibration_config is not None
                and self._confidence_calibration_config.enabled
            ):
                position = await self._store.get(position_id)
                agent_name = position.get("agent_name") if position else None
                if agent_name:
                    from learning.confidence_calibration import (
                        recompute_calibration_for_strategy,
                    )

                    analytics_rows = await self._analytics_store.list_by_strategy(
                        agent_name,
                        limit=5000,
                    )
                    await recompute_calibration_for_strategy(
                        agent_name,
                        analytics_rows,
                        self._confidence_calibration_store,
                        self._confidence_calibration_config,
                    )
        except Exception:
            _log.exception("Analytics derivation failed for position %s", position_id)

    async def close_by_reconciliation(
        self, position_id: int, exit_price: Decimal, exit_time: datetime
    ) -> None:
        await self._store.close_position(
            position_id,
            exit_price=str(exit_price),
            exit_fees=str(Decimal("0")),
            exit_time=exit_time.isoformat(),
            exit_reason="manual_close",
        )

    @staticmethod
    def compute_pnl(
        *,
        side: str,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        entry_fees: Decimal,
        exit_fees: Decimal,
    ) -> dict:
        if side.lower() == "buy":
            gross_pnl = (exit_price - entry_price) * quantity
        else:
            gross_pnl = (entry_price - exit_price) * quantity
        net_pnl = gross_pnl - entry_fees - exit_fees
        cost_basis = entry_price * quantity
        return_pct = float(net_pnl / cost_basis) if cost_basis else 0.0
        return {"gross_pnl": gross_pnl, "net_pnl": net_pnl, "return_pct": return_pct}
