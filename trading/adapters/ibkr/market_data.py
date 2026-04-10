import asyncio
from collections.abc import Callable
from decimal import Decimal
from datetime import datetime
from typing import Any

from ib_async import IB

from broker.interfaces import MarketDataProvider
from broker.models import (
    Bar,
    ContractDetails,
    OptionsChain,
    Quote,
    Symbol,
)
from adapters.ibkr.symbols import to_contract


class IBKRMarketDataProvider(MarketDataProvider):
    def __init__(self, ib: IB):
        self._ib = ib
        self._delayed_enabled = False

    async def _ensure_delayed_data(self) -> None:
        """Enable delayed market data for paper accounts without live subscriptions."""
        if not self._delayed_enabled:
            self._ib.reqMarketDataType(3)  # 3 = delayed
            self._delayed_enabled = True

    @staticmethod
    def _safe_decimal(val: float) -> Decimal | None:
        """Convert IB's NaN-as-float to Decimal or None."""
        if val != val or val is None:  # NaN check
            return None
        return Decimal(str(val))

    @staticmethod
    def _safe_int(val: float | None) -> int:
        if val is None or val != val:
            return 0
        return int(val)

    async def get_quote(self, symbol: Symbol) -> Quote:
        await self._ensure_delayed_data()
        contract = to_contract(symbol)
        await self._ib.qualifyContractsAsync(contract)
        ticker = self._ib.reqMktData(contract, snapshot=True)
        # Poll until data arrives (async-safe, no event loop conflict)
        for _ in range(10):
            await asyncio.sleep(0.5)
            if ticker.last == ticker.last and ticker.last is not None:
                break
        self._ib.cancelMktData(contract)
        return Quote(
            symbol=symbol,
            bid=self._safe_decimal(ticker.bid),
            ask=self._safe_decimal(ticker.ask),
            last=self._safe_decimal(ticker.last),
            volume=self._safe_int(ticker.volume),
            timestamp=datetime.now(),
        )

    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]:
        return [await self.get_quote(s) for s in symbols]

    async def stream_quotes(
        self,
        symbols: list[Symbol],
        callback: Callable[[Quote], Any],
    ) -> None:
        await self._ensure_delayed_data()
        for symbol in symbols:
            contract = to_contract(symbol)
            await self._ib.qualifyContractsAsync(contract)
            ticker = self._ib.reqMktData(contract)

            def on_update(t, sym=symbol):
                q = Quote(
                    symbol=sym,
                    bid=self._safe_decimal(t.bid),
                    ask=self._safe_decimal(t.ask),
                    last=self._safe_decimal(t.last),
                    volume=self._safe_int(t.volume),
                    timestamp=datetime.now(),
                )
                callback(q)

            ticker.updateEvent += on_update

    async def get_historical(
        self,
        symbol: Symbol,
        timeframe: str,
        period: str,
    ) -> list[Bar]:
        contract = to_contract(symbol)
        await self._ib.qualifyContractsAsync(contract)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=period,
            barSizeSetting=timeframe,
            whatToShow="TRADES",
            useRTH=True,
        )
        return [
            Bar(
                symbol=symbol,
                open=Decimal(str(b.open)),
                high=Decimal(str(b.high)),
                low=Decimal(str(b.low)),
                close=Decimal(str(b.close)),
                volume=self._safe_int(b.volume),
                timestamp=b.date
                if isinstance(b.date, datetime)
                else datetime.combine(b.date, datetime.min.time()),
            )
            for b in (bars or [])
        ]

    async def get_options_chain(
        self,
        symbol: Symbol,
        expiry: str | None = None,
    ) -> OptionsChain:
        contract = to_contract(
            Symbol(ticker=symbol.ticker, asset_type=symbol.asset_type)
        )
        await self._ib.qualifyContractsAsync(contract)
        chains = await self._ib.reqSecDefOptParamsAsync(
            contract.symbol,
            "",
            contract.secType,
            contract.conId,
        )
        chain = chains[0] if chains else None
        if not chain:
            return OptionsChain(symbol=symbol)

        from datetime import date

        expirations = [
            date(int(e[:4]), int(e[4:6]), int(e[6:8])) for e in chain.expirations
        ]
        strikes = [Decimal(str(s)) for s in chain.strikes]
        return OptionsChain(symbol=symbol, expirations=expirations, strikes=strikes)

    async def get_contract_details(self, symbol: Symbol) -> ContractDetails:
        contract = to_contract(symbol)
        await self._ib.qualifyContractsAsync(contract)
        details_list = await self._ib.reqContractDetailsAsync(contract)
        if not details_list:
            from broker.errors import InvalidSymbol

            raise InvalidSymbol(f"No contract found for {symbol.ticker}")
        d = details_list[0]
        return ContractDetails(
            symbol=symbol,
            long_name=d.longName or "",
            industry=d.industry or "",
            category=d.category or "",
            min_tick=Decimal(str(d.minTick)) if d.minTick else Decimal("0.01"),
            trading_hours=d.tradingHours or "",
        )
