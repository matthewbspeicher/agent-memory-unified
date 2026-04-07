"""TaoshiSignalReplay — provides chronological iteration over historical Taoshi positions."""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from agents.models import AgentSignal

logger = logging.getLogger(__name__)


class TaoshiSignalReplay:
    """Loads closed Taoshi positions from disk and yields them as Signal objects."""

    def __init__(self, taoshi_root: str | Path) -> None:
        self._root = Path(taoshi_root)
        self._signals: list[AgentSignal] = []
        self._index = 0
        self._load_signals()

    def _load_signals(self) -> None:
        """Scan validation/miners/*/positions/*/closed/ for signals."""
        miners_dir = self._root / "validation" / "miners"
        if not miners_dir.exists():
            logger.warning("Taoshi miners directory not found: %s", miners_dir)
            return

        raw_signals = []
        for miner_dir in miners_dir.iterdir():
            if not miner_dir.is_dir():
                continue

            hotkey = miner_dir.name
            positions_dir = miner_dir / "positions"
            if not positions_dir.exists():
                continue

            for symbol_dir in positions_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue

                symbol = symbol_dir.name
                closed_dir = symbol_dir / "closed"
                if not closed_dir.exists():
                    continue

                for pos_file in closed_dir.iterdir():
                    if not pos_file.is_file():
                        continue

                    try:
                        with open(pos_file, "r") as f:
                            data = json.load(f)

                        # Use open_ms as the signal timestamp
                        open_ms = data.get("open_ms", 0)
                        ts = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc)

                        # Extract initial direction from first order
                        orders = data.get("orders", [])
                        if not orders:
                            continue

                        first_order = orders[0]
                        order_type = first_order.get("order_type", "FLAT")
                        leverage = first_order.get("leverage", 0.0)
                        price = first_order.get("price", 0.0)

                        direction = "flat"
                        if order_type == "LONG":
                            direction = "long"
                        elif order_type == "SHORT":
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
                                "position_uuid": data.get("position_uuid", ""),
                                "order_type": order_type,
                                "open_ms": open_ms,
                                "signal_reason": "new_position",
                                "order_count": len(orders),
                            },
                            expires_at=ts + timedelta(hours=24),  # Dummy for backtest
                        )
                        # We temporarily attach the timestamp for sorting
                        setattr(signal, "_backtest_ts", ts)
                        raw_signals.append(signal)

                    except Exception as e:
                        logger.warning("Failed to load position %s: %s", pos_file, e)

        # Sort all signals by their historical timestamp
        self._signals = sorted(raw_signals, key=lambda s: getattr(s, "_backtest_ts"))
        logger.info("Loaded %d historical signals from Taoshi data", len(self._signals))

    def __len__(self) -> int:
        return len(self._signals)

    def get_signals_before(self, timestamp: datetime) -> list[AgentSignal]:
        """Yield all signals that occurred up to and including the given timestamp."""
        result = []
        while self._index < len(self._signals):
            signal = self._signals[self._index]
            if getattr(signal, "_backtest_ts") <= timestamp:
                result.append(signal)
                self._index += 1
            else:
                break
        return result

    def reset(self) -> None:
        self._index = 0
