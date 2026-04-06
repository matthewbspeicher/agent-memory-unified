"""Historical data replay — provides bar-by-bar iteration for backtesting."""

from __future__ import annotations
import logging
from datetime import datetime

from broker.models import Bar

logger = logging.getLogger(__name__)


class HistoricalReplay:
    """Yields synchronized bars across multiple symbols, ordered by timestamp."""

    def __init__(self, data: dict[str, list[Bar]]) -> None:
        """
        Args:
            data: mapping of ticker -> list[Bar] (must be sorted by timestamp ascending)
        """
        self._data = data
        self._indices: dict[str, int] = {ticker: 0 for ticker in data}
        self._length = min(len(bars) for bars in data.values()) if data else 0

    @property
    def length(self) -> int:
        return self._length

    @property
    def tickers(self) -> list[str]:
        return list(self._data.keys())

    def __len__(self) -> int:
        return self._length

    def get_bar(self, ticker: str, offset: int = 0) -> Bar | None:
        """Get a bar for a ticker at current index + offset."""
        idx = self._indices.get(ticker, 0) + offset
        bars = self._data.get(ticker, [])
        if 0 <= idx < len(bars):
            return bars[idx]
        return None

    def get_bars_at(self, index: int) -> dict[str, Bar]:
        """Get all bars at a specific index (regardless of current position)."""
        result = {}
        for ticker, bars in self._data.items():
            if 0 <= index < len(bars):
                result[ticker] = bars[index]
        return result

    def current_bars(self) -> dict[str, Bar]:
        """Get bars at current replay position."""
        return self.get_bars_at_current()

    def get_bars_at_current(self) -> dict[str, Bar]:
        """Get all bars at the current replay position."""
        return {
            t: bars[idx]
            for t, bars in self._data.items()
            if (idx := self._indices.get(t, 0)) < len(bars)
        }

    def current_timestamp(self) -> datetime | None:
        """Get the timestamp of the current bar (uses first ticker's bar)."""
        bars = self.current_bars()
        if bars:
            return list(bars.values())[0].timestamp
        return None

    def advance(self) -> dict[str, Bar] | None:
        """Advance all tickers by one bar. Returns bars or None if exhausted."""
        if any(
            idx >= len(bars)
            for bars, idx in zip(self._data.values(), self._indices.values())
        ):
            return None

        result = self.current_bars()
        for ticker in self._indices:
            self._indices[ticker] += 1
        return result

    def seek(self, index: int) -> None:
        """Jump to a specific index."""
        for ticker in self._indices:
            self._indices[ticker] = min(index, len(self._data.get(ticker, [])))

    def reset(self) -> None:
        """Reset all tickers to the beginning."""
        self._indices = {ticker: 0 for ticker in self._data}

    def slice(self, start: int, end: int | None = None) -> "HistoricalReplay":
        """Create a new replay from a slice of the data."""
        end = end or self._length
        sliced = {}
        for ticker, bars in self._data.items():
            sliced[ticker] = bars[start:end]
        return HistoricalReplay(sliced)

    @classmethod
    def from_bars_dict(cls, bars_by_ticker: dict[str, list[Bar]]) -> "HistoricalReplay":
        """Create from a dict of ticker -> bars. Ensures bars are sorted."""
        sorted_data = {}
        for ticker, bars in bars_by_ticker.items():
            sorted_data[ticker] = sorted(bars, key=lambda b: b.timestamp)
        return cls(sorted_data)
