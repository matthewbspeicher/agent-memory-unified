from __future__ import annotations

from broker.interfaces import Broker
from broker.models import Bar, OptionsChain, Quote, Symbol
from data.sources.base import DataSource


class BrokerSource(DataSource):
    name = "broker"
    supports_quotes = True
    supports_historical = True
    supports_options = True
    supports_fundamentals = False

    def __init__(self, broker: Broker) -> None:
        self._broker = broker

    async def get_quote(self, symbol: Symbol) -> Quote:
        return await self._broker.market_data.get_quote(symbol)

    async def get_historical(
        self,
        symbol: Symbol,
        timeframe: str = "1d",
        period: str = "3mo",
    ) -> list[Bar]:
        return await self._broker.market_data.get_historical(symbol, timeframe, period)

    async def get_options_chain(self, symbol: Symbol) -> OptionsChain:
        return await self._broker.market_data.get_options_chain(symbol)
