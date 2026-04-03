from __future__ import annotations
from datetime import timedelta

from integrations.bittensor.models import DerivedBittensorView, RawMinerForecast
from storage.bittensor import BittensorStore


class BittensorDataSource:
    """Read-only agent-facing facade over BittensorStore.

    Does not speak subtensor, dendrite, or synapse classes.
    """

    def __init__(self, store: BittensorStore) -> None:
        self._store = store

    async def get_latest_signal(
        self, symbol: str, timeframe: str,
    ) -> DerivedBittensorView | None:
        return await self._store.get_latest_view(symbol, timeframe)

    async def get_signal_history(
        self, symbol: str, timeframe: str, hours: int = 24,
    ) -> list[DerivedBittensorView]:
        latest = await self.get_latest_signal(symbol, timeframe)
        if latest is None:
            return []
        since = latest.timestamp - timedelta(hours=hours)
        return await self._store.get_view_history(symbol, timeframe, since)

    async def get_recent_raw_forecasts(
        self, symbol: str, timeframe: str, window_id: str,
    ) -> list[RawMinerForecast]:
        rows = await self._store.get_raw_forecasts_by_window(window_id)
        return [
            row for row in rows
            if row.symbol == symbol and row.timeframe == timeframe
        ]
