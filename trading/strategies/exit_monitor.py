"""ExitMonitorAgent — scans open tracked positions and emits exit opportunities."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import (
    AssetType,
    MarketOrder,
    OrderBase,
    OrderSide,
    StopOrder,
    Symbol,
    TrailingStopOrder,
)
from exits.rules import StopLoss, TrailingStop

if TYPE_CHECKING:
    from data.bus import DataBus
    from exits.manager import ExitManager
    from storage.pnl import TrackedPositionStore

logger = logging.getLogger(__name__)


_PREDICTION_BROKERS = {"kalshi", "kalshi_paper", "polymarket", "polymarket_paper"}


class ExitMonitorAgent(StructuredAgent):
    """Scans open tracked positions for triggered exit rules and emits SELL opportunities.

    Requires injection of an ExitManager and a TrackedPositionStore at construction
    time so it can check persisted exit rules against current market prices.

    Each triggered opportunity has ``is_exit=True`` so the router skips the
    SizingEngine and uses the full position quantity instead.
    """

    def __init__(
        self,
        config,
        exit_manager: "ExitManager | None" = None,
        position_store: "TrackedPositionStore | None" = None,
    ) -> None:
        super().__init__(config)
        self._exit_manager = exit_manager
        self._position_store = position_store
        self._exit_cooldown: dict[int | str, datetime] = {}
        self._cooldown_seconds: int = int(
            config.parameters.get("exit_cooldown_seconds", 300)
        )

    @property
    def description(self) -> str:
        return (
            "Scans open positions for triggered exit rules and emits SELL opportunities"
        )

    async def scan(self, data: "DataBus") -> list[Opportunity]:
        if not self._exit_manager or not self._position_store:
            logger.warning(
                "ExitMonitorAgent '%s' missing exit_manager or position_store — skipping scan",
                self.name,
            )
            return []

        # Purge expired cooldowns
        now_pre = datetime.now(timezone.utc)
        self._exit_cooldown = {
            pid: ts
            for pid, ts in self._exit_cooldown.items()
            if (now_pre - ts).total_seconds() < self._cooldown_seconds
        }

        # Load all open tracked positions
        open_positions = await self._position_store.list_open()
        if not open_positions:
            return []

        # Batch-fetch quotes for all unique symbols
        symbols_seen: dict[str, Symbol] = {}
        for pos in open_positions:
            ticker = pos["symbol"]
            if ticker not in symbols_seen:
                # Prediction-market tickers are treated as PREDICTION asset type
                asset_type = (
                    AssetType.PREDICTION
                    if pos.get("broker_id") in _PREDICTION_BROKERS
                    else AssetType.STOCK
                )
                symbols_seen[ticker] = Symbol(ticker=ticker, asset_type=asset_type)

        quotes: dict[str, Decimal] = {}
        for ticker, sym in symbols_seen.items():
            try:
                quote = await data.get_quote(sym)
                if quote and quote.last is not None:
                    quotes[ticker] = quote.last
            except Exception as exc:
                logger.warning(
                    "ExitMonitor: failed to fetch quote for %s: %s", ticker, exc
                )

        now = datetime.now(timezone.utc)
        opportunities: list[Opportunity] = []

        for pos in open_positions:
            position_id = pos["id"]
            ticker = pos["symbol"]
            current_price = quotes.get(ticker)
            if current_price is None:
                logger.debug(
                    "ExitMonitor: no quote for %s, skipping position %d",
                    ticker,
                    position_id,
                )
                continue

            side_str = str(pos.get("side", "BUY")).upper()
            entry_price = (
                Decimal(pos["entry_price"]) if pos.get("entry_price") else None
            )

            self._exit_manager.update_trailing(position_id, current_price)

            triggered = self._exit_manager.check(
                position_id=position_id,
                current_price=current_price,
                current_time=now,
                entry_price=entry_price,
                side=side_str,
            )
            if triggered is None:
                continue

            # Cooldown: skip if we already emitted an exit for this position recently
            last_emit = self._exit_cooldown.get(position_id)
            if last_emit and (now - last_emit).total_seconds() < self._cooldown_seconds:
                logger.debug(
                    "ExitMonitor: position %d (%s) on cooldown — skipping (rule=%s)",
                    position_id,
                    ticker,
                    triggered.name,
                )
                continue

            # Determine exit side (reverse of entry)
            order_side = OrderSide.SELL if side_str == "BUY" else OrderSide.BUY
            quantity = Decimal(str(pos.get("entry_quantity", 1)))

            sym = symbols_seen[ticker]
            account_id = pos.get("account_id", "") or ""
            suggested_trade: OrderBase
            if isinstance(triggered, StopLoss):
                suggested_trade = StopOrder(
                    symbol=sym,
                    side=order_side,
                    quantity=quantity,
                    account_id=account_id,
                    stop_price=triggered.stop_price,
                )
            elif isinstance(triggered, TrailingStop):
                suggested_trade = TrailingStopOrder(
                    symbol=sym,
                    side=order_side,
                    quantity=quantity,
                    account_id=account_id,
                    trail_percent=triggered.trail_pct * Decimal("100"),
                )
            else:
                suggested_trade = MarketOrder(
                    symbol=sym,
                    side=order_side,
                    quantity=quantity,
                    account_id=account_id,
                )

            opp = Opportunity(
                id=f"{self.name}_{ticker}_{position_id}_{int(now.timestamp())}",
                agent_name=self.name,
                symbol=sym,
                signal="exit_position",
                confidence=1.0,
                reasoning=f"Exit rule triggered: {triggered.name} (position_id={position_id})",
                data={
                    "tracked_position_id": position_id,
                    "position_id": position_id,
                    "exit_rule": triggered.name,
                    "entry_price": str(entry_price) if entry_price else None,
                    "current_price": str(current_price),
                    "side": side_str,
                },
                timestamp=now,
                suggested_trade=suggested_trade,
                broker_id=pos.get("broker_id"),
                is_exit=True,
            )
            opportunities.append(opp)
            self._exit_cooldown[position_id] = now
            logger.info(
                "ExitMonitor: exit triggered for position %d (%s) via rule '%s'",
                position_id,
                ticker,
                triggered.name,
            )

        return opportunities
