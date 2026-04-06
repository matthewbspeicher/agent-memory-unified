from __future__ import annotations
from abc import ABC, abstractmethod

from broker.models import Bar, OptionsChain, Quote, Symbol


class DataSource(ABC):
    name: str
    supports_quotes: bool = False
    supports_historical: bool = False
    supports_options: bool = False
    supports_fundamentals: bool = False

    @abstractmethod
    async def get_quote(self, symbol: Symbol) -> Quote: ...

    @abstractmethod
    async def get_historical(
        self,
        symbol: Symbol,
        timeframe: str = "1d",
        period: str = "3mo",
    ) -> list[Bar]: ...

    @abstractmethod
    async def get_options_chain(self, symbol: Symbol) -> OptionsChain: ...
