from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from observability.alerting import AlertRouter
    from storage.performance import PerformanceSnapshot

logger = logging.getLogger(__name__)


@dataclass
class TradeEvent:
    agent_name: str
    symbol: str
    action: str          # buy / sell / short / cover
    fill_price: float
    expected_price: float
    slippage_bps: int
    commission: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ObservabilityEmitter:
    """Writes events to Supabase and routes alerts by tier.

    Instantiate with a supabase AsyncClient and an AlertRouter.
    Call start() inside the FastAPI lifespan to begin EventBus subscription.
    """

    def __init__(
        self,
        supabase_client: Any,
        alert_router: "AlertRouter",
    ) -> None:
        self._sb = supabase_client
        self._alert_router = alert_router
        self._listen_task: asyncio.Task | None = None

    def start(self, event_bus: Any) -> None:
        """Subscribe to EventBus and start listening for events."""
        self._listen_task = asyncio.create_task(self._listen(event_bus))

    def stop(self) -> None:
        if self._listen_task:
            self._listen_task.cancel()

    async def emit(
        self,
        event_type: str,
        level: str,
        agent_name: str | None,
        message: str,
        metadata: dict,
    ) -> None:
        row = {
            "level": level,
            "event_type": event_type,
            "agent_name": agent_name,
            "message": message,
            "metadata": metadata,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._sb_insert("system_events", row)
        if level in ("critical", "warning"):
            await self._alert_router.fire(level, event_type, message, metadata)

    async def emit_trade(self, trade_event: TradeEvent) -> None:
        row = {
            "agent_name": trade_event.agent_name,
            "symbol": trade_event.symbol,
            "action": trade_event.action,
            "fill_price": str(trade_event.fill_price),
            "expected_price": str(trade_event.expected_price),
            "slippage_bps": trade_event.slippage_bps,
            "commission": str(trade_event.commission),
            "timestamp": trade_event.timestamp.isoformat(),
        }
        await self._sb_insert("trade_events", row)

    async def heartbeat(self, agent_name: str, status: str, cycle_count: int = 0) -> None:
        row = {
            "agent_name": agent_name,
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "cycle_count": cycle_count,
        }
        try:
            await (
                self._sb.table("agent_heartbeats")
                .upsert(row, on_conflict="agent_name")
                .execute()
            )
        except Exception:
            logger.exception("ObservabilityEmitter.heartbeat failed for %s", agent_name)

    async def snapshot_metrics(
        self, agent_name: str, snapshot: "PerformanceSnapshot"
    ) -> None:
        row = {
            "agent_name": agent_name,
            "sharpe": float(snapshot.sharpe_ratio),
            "win_rate": float(snapshot.win_rate),
            "max_drawdown": float(snapshot.max_drawdown),
            "trade_count": snapshot.total_trades,
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._sb_insert("metric_snapshots", row)

    async def _sb_insert(self, table: str, row: dict) -> None:
        try:
            await self._sb.table(table).insert(row).execute()
        except Exception:
            logger.exception("ObservabilityEmitter failed to insert into %s", table)

    async def _listen(self, event_bus: Any) -> None:
        """Translate EventBus events into observability emit calls."""
        try:
            async for event in event_bus.subscribe():
                topic: str = event.get("topic", "")
                data: dict = event.get("data", {})
                await self._handle_event(topic, data)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("ObservabilityEmitter._listen crashed")

    async def _handle_agent_signal(self, data: dict) -> None:
        """Persist an agent_signal event to the agent_signals Supabase table."""
        row = {
            "source_agent": data.get("source_agent"),
            "target_agent": data.get("target_agent"),
            "signal_type": data.get("signal_type"),
            "payload": data.get("payload", {}),
            "expires_at": data.get("expires_at"),
            "timestamp": data.get("timestamp"),
        }
        await self._sb_insert("agent_signals", row)

    async def _handle_event(self, topic: str, data: dict) -> None:
        """Map known EventBus topics to observability emit calls."""
        if topic == "agent_signal":
            await self._handle_agent_signal(data)
            return

        level_map: dict[str, str] = {
            "kill_switch_triggered": "critical",
            "broker_disconnected": "critical",
            "agent_crashed": "critical",
            "drawdown_breach": "critical",
            "order_rejected": "critical",
            "slippage_elevated": "warning",
            "agent_idle": "warning",
            "fill_rate_degrading": "warning",
            "api_error_rate_elevated": "warning",
            "agent_run_complete": "info",
            "trade_executed": "info",
            "opportunity_found": "info",
        }
        level = level_map.get(topic, "info")
        agent_name: str | None = data.get("agent_name")
        message = data.get("message") or f"{topic}: {data}"
        await self.emit(
            event_type=topic,
            level=level,
            agent_name=agent_name,
            message=message,
            metadata=data,
        )
