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
        knowledge_graph: Any | None = None,
        kg_enabled: bool = False,
        stale_threshold_seconds: float = 3600.0,
    ):
        self._root = Path(taoshi_root)
        self._miners_dir = self._root / "validation" / "miners"
        self._store = store
        self._signal_bus = signal_bus
        self._event_bus = event_bus
        self._poll_interval = poll_interval
        self._knowledge_graph = knowledge_graph
        self._kg_enabled = kg_enabled
        self._stale_threshold = timedelta(seconds=stale_threshold_seconds)
        self._running = False
        self._initialized_from_store: set[str] = set()

        # Track what we've already seen — maps {uuid: content_hash | None}
        # None means loaded from store but not yet seen on disk (warm-start sentinel)
        # Change detection: emit signal when UUID is new OR hash changed
        self._seen_positions: dict[str, str | None] = {}
        # Map uuid -> (hotkey, symbol) for KG invalidation on position close
        self._position_context: dict[str, tuple[str, str]] = {}
        self._last_scan_at: datetime | None = None

        # Per-miner churn tracking — last_seen timestamp per hotkey and the
        # set of hotkeys observed on the previous poll. Lets us surface
        # "miner went silent" before their ranking tanks.
        self._miner_last_seen: dict[str, datetime] = {}
        self._prev_poll_miners: set[str] = set()

        # Stats
        self.miners_tracked: int = 0
        self.open_positions: int = 0
        self.signals_emitted: int = 0
        self.updates_detected: int = 0
        # Churn stats (updated on each poll)
        self.miners_new_last_poll: int = 0
        self.miners_disappeared_last_poll: int = 0

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
                    # None sentinel means loaded from store; hash will be set on first poll.
                    self._seen_positions[uuid] = None
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

        now = datetime.now(timezone.utc)
        miners = [d for d in self._miners_dir.iterdir() if d.is_dir()]
        self.miners_tracked = len(miners)

        total_open = 0
        new_signals = 0

        current_uuids: set[str] = set()
        current_poll_miners: set[str] = set()

        for miner_dir in miners:
            hotkey = miner_dir.name
            current_poll_miners.add(hotkey)
            self._miner_last_seen[hotkey] = now
            
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
                                self._position_context[uuid] = (hotkey, symbol)
                                await self._emit_signal(
                                    pos,
                                    hotkey,
                                    symbol,
                                    signal_reason="new_position",
                                )
                                new_signals += 1
                                if self._knowledge_graph and self._kg_enabled:
                                    try:
                                        await self._knowledge_graph.add_triple(
                                            f"miner_{hotkey[:8]}",
                                            "signal_on",
                                            symbol,
                                            valid_from=datetime.now(
                                                timezone.utc
                                            ).strftime("%Y-%m-%d"),
                                            source="bridge",
                                        )
                                    except Exception:
                                        pass  # KG writes are best-effort, never block polling
                            elif uuid in self._initialized_from_store:
                                # Position loaded from prior store state; initialize current
                                # hash without re-emitting a duplicate signal.
                                self._seen_positions[uuid] = content_hash
                                self._position_context[uuid] = (hotkey, symbol)
                                self._initialized_from_store.discard(uuid)
                            elif prev_hash != content_hash:
                                # Position updated (new orders, leverage change, etc.)
                                self._seen_positions[uuid] = content_hash
                                self._position_context[uuid] = (hotkey, symbol)
                                await self._emit_signal(
                                    pos,
                                    hotkey,
                                    symbol,
                                    signal_reason="position_updated",
                                )
                                new_signals += 1
                                self.updates_detected += 1

        # Churn detection
        if self._prev_poll_miners:
            new_miners = current_poll_miners - self._prev_poll_miners
            disappeared_miners = self._prev_poll_miners - current_poll_miners
            self.miners_new_last_poll = len(new_miners)
            self.miners_disappeared_last_poll = len(disappeared_miners)
            
            if new_miners or disappeared_miners:
                logger.info(
                    "TaoshiBridge churn: +%d new, -%d disappeared miners",
                    len(new_miners),
                    len(disappeared_miners),
                )
        
        self._prev_poll_miners = current_poll_miners

        # Clean up positions no longer on disk (moved to closed/)
        stale_uuids = set(self._seen_positions.keys()) - current_uuids
        for uuid in stale_uuids:
            # KG invalidation for closed positions
            if self._knowledge_graph and self._kg_enabled and uuid in self._position_context:
                hotkey, symbol = self._position_context[uuid]
                try:
                    await self._knowledge_graph.invalidate(
                        f"miner_{hotkey[:8]}",
                        "signal_on",
                        symbol,
                        ended=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        reason="position_closed",
                    )
                except Exception:
                    pass  # KG writes are best-effort, never block polling
            del self._seen_positions[uuid]
            self._position_context.pop(uuid, None)
            self._initialized_from_store.discard(uuid)
        if stale_uuids:
            logger.debug(
                "TaoshiBridge: cleaned %d closed positions from tracking",
                len(stale_uuids),
            )

        self.open_positions = total_open
        self._last_scan_at = now

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

    def _read_position(self, path: Path) -> dict[str, Any] | None:
        """Read a Taoshi position JSON file.

        Implements retry logic to handle transient partial writes from the validator.
        """
        import time

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError as exc:
                if attempt == max_retries - 1:
                    logger.warning(
                        "Failed to parse position %s after %d attempts: %s",
                        path,
                        max_retries,
                        exc,
                    )
                    return None
                logger.debug(
                    "JSON decode error on %s, retrying (attempt %d): %s",
                    path,
                    attempt + 1,
                    exc,
                )
                time.sleep(0.1)
            except Exception as exc:
                logger.warning("Failed to read position %s: %s", path, exc)
                return None
        return None

    @staticmethod
    def _hash_position(position: dict[str, Any]) -> str:
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
        position: dict[str, Any],
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

    def get_status(self) -> dict[str, Any]:
        """Return bridge status for API/dashboard."""
        now = datetime.now(timezone.utc)
        stale_miners = [
            hk for hk, last_seen in self._miner_last_seen.items()
            if now - last_seen > self._stale_threshold
        ]
        
        return {
            "running": self._running,
            "taoshi_root": str(self._root),
            "miners_tracked": self.miners_tracked,
            "miners_new_last_poll": self.miners_new_last_poll,
            "miners_disappeared_last_poll": self.miners_disappeared_last_poll,
            "stale_miners_count": len(stale_miners),
            "open_positions": self.open_positions,
            "signals_emitted": self.signals_emitted,
            "last_scan_at": (
                self._last_scan_at.isoformat() if self._last_scan_at else None
            ),
            "seen_positions": len(self._seen_positions),
            "updates_detected": self.updates_detected,
        }

    def get_stale_miners(self) -> list[dict[str, Any]]:
        """Return a list of miners that haven't been seen recently."""
        now = datetime.now(timezone.utc)
        stale = []
        for hk, last_seen in self._miner_last_seen.items():
            delta = now - last_seen
            if delta > self._stale_threshold:
                stale.append({
                    "hotkey": hk,
                    "last_seen": last_seen.isoformat(),
                    "seconds_since_seen": delta.total_seconds()
                })
        return sorted(stale, key=lambda x: x["seconds_since_seen"], reverse=True)

    async def get_miner_summary(self) -> list[dict[str, Any]]:
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
