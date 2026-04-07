"""Bridge between official Taoshi PTN validator and our trading engine.

Polls the Taoshi validator's on-disk position data (validation/miners/)
and feeds miner signals into the SignalBus + BittensorStore so existing
strategies and the dashboard can consume them.

Change Detection (TP-001):
    Uses hash-based change tracking instead of a simple seen-set.
    ``_seen_positions`` maps ``{uuid: content_hash}`` where the hash is
    derived from order count, latest order timestamp, and latest leverage.
    A signal is emitted when:
      - A UUID is encountered for the first time (``signal_reason='new_position'``)
      - A known UUID's content hash has changed (``signal_reason='position_updated'``)
    Positions that disappear from disk (moved to ``closed/``) are pruned
    from the tracking dict to prevent unbounded memory growth.

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
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from utils.logging import log_event

logger = logging.getLogger(__name__)


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
        self._initialized_from_store: set[str] = set()

        # Track what we've already seen — maps {uuid: content_hash}
        # Change detection: emit signal when UUID is new OR hash changed
        self._seen_positions: dict[str, str] = {}
        self._last_scan_at: datetime | None = None

        # Stats
        self.miners_tracked: int = 0
        self.open_positions: int = 0
        self.signals_emitted: int = 0
        self.updates_detected: int = 0

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
                self._initialized_from_store = set(existing)
                # Load existing UUIDs into hash-based tracking (mark all as "seen" with empty hash)
                for uuid in existing:
                    # Empty hash means loaded from store; hash will be refreshed on first poll.
                    self._seen_positions[uuid] = ""
                logger.info(
                    "TaoshiBridge: loaded %d seen positions from store", len(existing)
                )
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

        current_uuids: set[str] = set()

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
                            current_uuids.add(uuid)
                            pos = self._read_position(pos_file)
                            if pos is None:
                                continue
                            content_hash = self._hash_position(pos)
                            prev_hash = self._seen_positions.get(uuid)
                            if prev_hash is None:
                                # New position
                                self._seen_positions[uuid] = content_hash
                                await self._emit_signal(
                                    pos,
                                    hotkey,
                                    symbol,
                                    signal_reason="new_position",
                                )
                                new_signals += 1
                            elif uuid in self._initialized_from_store:
                                # Position loaded from prior store state; initialize current
                                # hash without re-emitting a duplicate signal.
                                self._seen_positions[uuid] = content_hash
                                self._initialized_from_store.discard(uuid)
                            elif prev_hash != content_hash:
                                # Position updated (new orders, leverage change, etc.)
                                self._seen_positions[uuid] = content_hash
                                await self._emit_signal(
                                    pos,
                                    hotkey,
                                    symbol,
                                    signal_reason="position_updated",
                                )
                                new_signals += 1
                                self.updates_detected += 1

        # Clean up positions no longer on disk (moved to closed/)
        stale_uuids = set(self._seen_positions.keys()) - current_uuids
        for uuid in stale_uuids:
            del self._seen_positions[uuid]
            self._initialized_from_store.discard(uuid)
        if stale_uuids:
            logger.debug(
                "TaoshiBridge: cleaned %d closed positions from tracking",
                len(stale_uuids),
            )

        self.open_positions = total_open
        self._last_scan_at = datetime.now(timezone.utc)

        if new_signals > 0:
            log_event(
                logger,
                logging.INFO,
                "bridge.poll",
                "TaoshiBridge: %d new signals from %d miners (%d open positions total)"
                % (new_signals, self.miners_tracked, total_open),
                data={
                    "new_signals": new_signals,
                    "miners": self.miners_tracked,
                    "open_positions": total_open,
                },
            )
        else:
            log_event(
                logger,
                logging.DEBUG,
                "bridge.poll",
                "TaoshiBridge: poll complete, no new signals",
                data={
                    "miners": self.miners_tracked,
                    "open_positions": total_open,
                },
            )

    def _read_position(self, path: Path) -> dict | None:
        """Read a Taoshi position JSON file."""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to read position %s: %s", path, exc)
            return None

    @staticmethod
    def _hash_position(position: dict) -> str:
        """Compute a content hash for change detection.

        Hash is based on order count, latest order timestamp, and latest
        leverage — the fields most likely to change when a position is
        updated.  Deterministic for the same position state.
        """
        orders = position.get("orders", [])
        order_count = len(orders)
        if orders:
            latest = orders[-1]
            latest_ts = latest.get("processed_ms", latest.get("price_sources_ts", 0))
            latest_leverage = latest.get("leverage", 0.0)
        else:
            latest_ts = 0
            latest_leverage = 0.0

        raw = f"{order_count}|{latest_ts}|{latest_leverage}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def _emit_signal(
        self,
        position: dict,
        hotkey: str,
        symbol: str,
        signal_reason: str = "new_position",
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
                "signal_reason": signal_reason,
                "order_count": len(orders),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        await self._signal_bus.publish(signal)
        self.signals_emitted += 1

        if self._store is not None:
            position_uuid = str(position.get("position_uuid", ""))
            if position_uuid:
                try:
                    await self._store.save_processed_position_uuid(
                        position_uuid, hotkey
                    )
                except Exception as exc:
                    logger.debug(
                        "TaoshiBridge: failed to persist processed position %s: %s",
                        position_uuid,
                        exc,
                    )

        log_event(
            logger,
            logging.INFO,
            "bridge.signal",
            "TaoshiBridge emitted signal: %s %s %s" % (hotkey[:12], symbol, direction),
            data={
                "miner_hotkey": hotkey[:12],
                "symbol": symbol,
                "direction": direction,
                "leverage": leverage,
            },
        )

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
            "seen_positions": len(self._seen_positions),
            "updates_detected": self.updates_detected,
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
