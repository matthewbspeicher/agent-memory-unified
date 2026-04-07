"""Bridge between official Taoshi PTN validator and our trading engine.

Polls the Taoshi validator's on-disk position data (validation/miners/)
and feeds miner signals into the SignalBus + BittensorStore so existing
strategies and the dashboard can consume them.

Architecture:
    Taoshi Validator (port 8091, receives miner signals)
        → writes positions to validation/miners/{hotkey}/positions/
    TaoshiBridge (this module)
        → polls those files periodically
        → converts to AgentSignal / DerivedBittensorView
        → publishes to SignalBus
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setLevel(logging.DEBUG)
    _h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(_h)


class TaoshiBridge:
    """Polls Taoshi validator disk data and bridges into trading engine."""

    def __init__(
        self,
        taoshi_root: str | Path,
        store: Any | None = None,
        signal_bus: Any | None = None,
        event_bus: Any | None = None,
        poll_interval: float = 30.0,
    ):
        self._root = Path(taoshi_root)
        self._miners_dir = self._root / "validation" / "miners"
        self._store = store
        self._signal_bus = signal_bus
        self._event_bus = event_bus
        self._poll_interval = poll_interval
        self._running = False

        # Track what we've already seen to avoid duplicates
        self._seen_position_uuids: set[str] = set()
        self._last_scan_at: datetime | None = None

        # Stats
        self.miners_tracked: int = 0
        self.open_positions: int = 0
        self.signals_emitted: int = 0

    async def run(self) -> None:
        """Main polling loop."""
        self._running = True
        logger.info(
            "TaoshiBridge started (root=%s, poll=%ss)",
            self._root,
            self._poll_interval,
        )

        if self._store:
            try:
                existing = await self._store.get_processed_position_uuids()
                self._seen_position_uuids.update(existing)
                logger.info("TaoshiBridge: loaded %d seen positions from store", len(existing))
            except Exception as exc:
                logger.error("TaoshiBridge: failed to load seen positions: %s", exc)

        while self._running:
            try:
                await self._poll()
            except Exception as exc:
                logger.error("TaoshiBridge poll error: %s", exc, exc_info=True)
            await asyncio.sleep(self._poll_interval)

        logger.info("TaoshiBridge stopped")

    def stop(self) -> None:
        self._running = False

    async def _poll(self) -> None:
        """Scan the validation/miners/ directory for position updates."""
        if not self._miners_dir.exists():
            logger.debug("Miners dir not found: %s", self._miners_dir)
            return

        miners = [d for d in self._miners_dir.iterdir() if d.is_dir()]
        self.miners_tracked = len(miners)

        total_open = 0
        new_signals = 0

        for miner_dir in miners:
            hotkey = miner_dir.name
            positions_dir = miner_dir / "positions"
            if not positions_dir.exists():
                continue

            for symbol_dir in positions_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                symbol = symbol_dir.name

                # Scan open positions
                open_dir = symbol_dir / "open"
                if open_dir.exists():
                    for pos_file in open_dir.iterdir():
                        if pos_file.is_file():
                            total_open += 1
                            uuid = pos_file.stem
                            if uuid not in self._seen_position_uuids:
                                self._seen_position_uuids.add(uuid)
                                pos = self._read_position(pos_file)
                                if pos:
                                    await self._emit_signal(pos, hotkey, symbol)
                                    if self._store:
                                        await self._store.save_processed_position_uuid(uuid, hotkey)
                                    new_signals += 1

        self.open_positions = total_open
        self._last_scan_at = datetime.now(timezone.utc)

        if new_signals > 0:
            logger.info(
                "TaoshiBridge: %d new signals from %d miners (%d open positions total)",
                new_signals,
                self.miners_tracked,
                total_open,
            )
        else:
            logger.debug(
                "TaoshiBridge: poll complete, %d miners, %d open positions, no new signals",
                self.miners_tracked,
                total_open,
            )

    def _read_position(self, path: Path) -> dict | None:
        """Read a Taoshi position JSON file."""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to read position %s: %s", path, exc)
            return None

    async def _emit_signal(
        self, position: dict, hotkey: str, symbol: str
    ) -> None:
        """Convert a Taoshi position into an AgentSignal and publish."""
        if not self._signal_bus:
            return

        from agents.models import AgentSignal

        # Extract direction from orders
        orders = position.get("orders", [])
        if not orders:
            return

        latest_order = orders[-1]
        order_type = latest_order.get("order_type", "FLAT")
        leverage = latest_order.get("leverage", 0.0)
        price = latest_order.get("price", 0.0)

        # Map Taoshi order types to our signal format
        direction = "flat"
        if order_type in ("LONG",):
            direction = "long"
        elif order_type in ("SHORT",):
            direction = "short"

        signal = AgentSignal(
            source_agent="taoshi_bridge",
            target_agent=None,
            signal_type="bittensor_miner_position",
            payload={
                "miner_hotkey": hotkey,
                "symbol": symbol,
                "direction": direction,
                "leverage": leverage,
                "price": price,
                "position_uuid": position.get("position_uuid", ""),
                "order_type": order_type,
                "open_ms": position.get("open_ms", 0),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        await self._signal_bus.publish(signal)
        self.signals_emitted += 1

    def get_status(self) -> dict:
        """Return bridge status for API/dashboard."""
        return {
            "running": self._running,
            "taoshi_root": str(self._root),
            "miners_tracked": self.miners_tracked,
            "open_positions": self.open_positions,
            "signals_emitted": self.signals_emitted,
            "last_scan_at": (
                self._last_scan_at.isoformat() if self._last_scan_at else None
            ),
            "seen_positions": len(self._seen_position_uuids),
        }

    async def get_miner_summary(self) -> list[dict]:
        """Get a summary of all tracked miners and their open positions."""
        if not self._miners_dir.exists():
            return []

        summaries = []
        for miner_dir in self._miners_dir.iterdir():
            if not miner_dir.is_dir():
                continue

            hotkey = miner_dir.name
            positions_dir = miner_dir / "positions"
            if not positions_dir.exists():
                continue

            open_count = 0
            closed_count = 0
            symbols = set()

            for symbol_dir in positions_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                symbols.add(symbol_dir.name)
                open_dir = symbol_dir / "open"
                closed_dir = symbol_dir / "closed"
                if open_dir.exists():
                    open_count += sum(1 for f in open_dir.iterdir() if f.is_file())
                if closed_dir.exists():
                    closed_count += sum(1 for f in closed_dir.iterdir() if f.is_file())

            summaries.append(
                {
                    "hotkey": hotkey,
                    "hotkey_short": hotkey[:12] + "...",
                    "symbols": sorted(symbols),
                    "open_positions": open_count,
                    "closed_positions": closed_count,
                }
            )

        return sorted(summaries, key=lambda x: x["open_positions"], reverse=True)
