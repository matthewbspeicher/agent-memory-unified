"""
MassiveDataSource — DataSource adapter wrapping MassiveClient.

Implements the DataSource interface (duck-typed to match YahooFinanceSource) so it
can be dropped into any DataBus ``sources`` list as a replacement for / supplement
to YahooFinanceSource.

Usage::

    client = MassiveClient(api_key=settings.massive_key)
    source = MassiveDataSource(client)
    data_bus = DataBus(sources=[source, broker_source], ...)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from broker.models import Bar, OptionsChain, Quote, Symbol
from data.sources.base import DataSource

logger = logging.getLogger(__name__)


class MassiveDataSource(DataSource):
    """
    DataSource backed by the Massive.com market data API.

    Replaces / supplements YahooFinanceSource for historical bars and live
    quotes. ``get_historical`` maps the DataBus ``timeframe`` / ``period``
    convention to Massive's ``multiplier`` / ``timespan`` / date-range.
    """

    name = "massive"
    supports_quotes = True
    supports_historical = True
    supports_options = False
    supports_fundamentals = False

    # ------------------------------------------------------------------
    # Period → date-offset helper
    # ------------------------------------------------------------------

    # Maps DataBus period strings to approximate calendar-day offsets.
    _PERIOD_DAYS: dict[str, int] = {
        "1d": 1,
        "5d": 5,
        "1mo": 30,
        "3mo": 90,
        "6mo": 180,
        "1y": 365,
        "2y": 730,
        "5y": 1825,
        "10y": 3650,
        "max": 3650,  # cap at 10 years; callers wanting more can use get_historical_bars directly
    }

    # Maps DataBus timeframe strings to Massive (Polygon) timespan + multiplier.
    _TIMEFRAME_MAP: dict[str, tuple[int, str]] = {
        "1m": (1, "minute"),
        "2m": (2, "minute"),
        "5m": (5, "minute"),
        "15m": (15, "minute"),
        "30m": (30, "minute"),
        "60m": (1, "hour"),
        "1h": (1, "hour"),
        "1d": (1, "day"),
        "1wk": (1, "week"),
        "1mo": (1, "month"),
    }

    def __init__(self, client) -> None:
        # Lazy import to avoid circular deps; caller passes MassiveClient.
        self._client = client
        # Free-tier lockout — Massive's snapshot endpoint is paid-only and
        # returns HTTP 403 "NOT_AUTHORIZED / not entitled to this data" on
        # every request. Without tracking that, every get_quote() call
        # pays the roundtrip + log line before falling through to the
        # next source. First 403 flips this flag; subsequent calls raise
        # immediately so DataBus can advance to yfinance without delay.
        # Rechecked on process restart — if the plan upgrades, operators
        # just restart to re-enable snapshots.
        self._snapshot_locked_out = False

    # ------------------------------------------------------------------
    # DataSource interface
    # ------------------------------------------------------------------

    async def get_quote(self, symbol: Symbol) -> Quote:
        """
        Fetch a live quote for *symbol* using the Massive snapshot endpoint.

        Falls back to ``get_quote`` (NBBO) if snapshot is unavailable.
        On free-tier accounts the snapshot endpoint is permanently 403;
        we detect that once and short-circuit every subsequent call.
        """
        if self._snapshot_locked_out:
            # Raise a sentinel error type DataBus recognizes as
            # "don't retry this source" so the log stays quiet.
            raise RuntimeError(
                "Massive snapshot disabled on current plan (paid-tier only)"
            )
        try:
            snap = await self._client.get_snapshot(symbol.ticker)
            day = snap.get("day", {}) or {}
            last_trade = snap.get("lastTrade", {}) or {}
            last_quote = snap.get("lastQuote", {}) or {}

            last_price = Decimal(str(last_trade.get("p", 0) or 0)) or Decimal(
                str(day.get("c", 0) or 0)
            )
            # Polygon lastQuote field convention: P = ask price, p = bid price
            ask = Decimal(str(last_quote.get("P", 0) or 0))
            bid = Decimal(str(last_quote.get("p", 0) or 0))
            volume = int(day.get("v", 0) or 0)

            # Timestamp: prefer last-trade time (nanoseconds → datetime)
            ts_ns = last_trade.get("t") or last_quote.get("t")
            if ts_ns:
                ts = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)
            else:
                ts = datetime.now(tz=timezone.utc)

            return Quote(
                symbol=symbol,
                bid=bid if bid else None,
                ask=ask if ask else None,
                last=last_price if last_price else None,
                volume=volume,
                timestamp=ts,
            )
        except Exception as exc:
            # Detect the free-tier 403 signature once and flip the
            # lockout so we stop hitting the endpoint. 403 and the
            # "NOT_AUTHORIZED" / "not entitled" phrase are the stable
            # markers; match loosely so minor response-shape drift
            # doesn't prevent the lockout.
            _msg = str(exc).lower()
            if (
                "403" in _msg
                or "not_authorized" in _msg
                or "not entitled" in _msg
                or "upgrade your plan" in _msg
            ):
                if not self._snapshot_locked_out:
                    logger.warning(
                        "MassiveDataSource.get_quote: snapshot endpoint "
                        "returned 403/NOT_AUTHORIZED for %s — free-tier "
                        "lockout, skipping snapshot for the rest of this "
                        "process. Upgrade Massive plan and restart to "
                        "re-enable. Falling back to yfinance for quotes.",
                        symbol.ticker,
                    )
                    self._snapshot_locked_out = True
                raise
            # Other errors (network, 5xx, etc.) — keep the original
            # WARNING so they stay visible.
            logger.warning(
                "MassiveDataSource.get_quote snapshot failed for %s: %s",
                symbol.ticker,
                exc,
            )
            raise

    async def get_historical(
        self, symbol: Symbol, timeframe: str = "1d", period: str = "3mo"
    ) -> list[Bar]:
        """
        Fetch historical OHLCV bars compatible with DataBus conventions.

        Translates DataBus ``timeframe`` / ``period`` strings into Massive
        ``multiplier`` / ``timespan`` / date-range parameters.
        """
        multiplier, timespan = self._TIMEFRAME_MAP.get(timeframe, (1, "day"))
        days = self._PERIOD_DAYS.get(period, 90)

        from datetime import timedelta

        today = datetime.now(tz=timezone.utc).date()
        from_date = (today - timedelta(days=days)).isoformat()
        to_date = today.isoformat()

        return await self.get_historical_bars(
            ticker=symbol.ticker,
            timespan=timespan,
            from_date=from_date,
            to_date=to_date,
            multiplier=multiplier,
            symbol=symbol,
        )

    async def get_options_chain(self, symbol: Symbol) -> OptionsChain:
        raise NotImplementedError("Use broker source for options data")

    # ------------------------------------------------------------------
    # Extended API (not part of DataSource ABC)
    # ------------------------------------------------------------------

    async def get_historical_bars(
        self,
        ticker: str,
        timespan: str,
        from_date: str,
        to_date: str,
        multiplier: int = 1,
        symbol: Symbol | None = None,
    ) -> list[Bar]:
        """
        Fetch historical OHLCV bars from Massive and convert to ``Bar`` objects.

        Args:
            ticker:     Uppercase ticker symbol.
            timespan:   Massive timespan string: ``"minute"``, ``"hour"``, ``"day"``, etc.
            from_date:  ISO date string ``"YYYY-MM-DD"``.
            to_date:    ISO date string ``"YYYY-MM-DD"``.
            multiplier: Multiplier for timespan (default 1).
            symbol:     Optional ``Symbol`` to embed in each Bar. Created from
                        *ticker* if not provided.

        Returns:
            Sorted list of :class:`~broker.models.Bar` instances.
        """
        if symbol is None:
            symbol = Symbol(ticker=ticker)

        raw = await self._client.get_bars(
            ticker, multiplier, timespan, from_date, to_date
        )
        bars: list[Bar] = []
        for r in raw:
            try:
                ts_ms: int = r["t"]
                ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                bar = Bar(
                    symbol=symbol,
                    timestamp=ts,
                    open=Decimal(str(r.get("o", 0))),
                    high=Decimal(str(r.get("h", 0))),
                    low=Decimal(str(r.get("l", 0))),
                    close=Decimal(str(r.get("c", 0))),
                    volume=int(r.get("v", 0)),
                )
                bars.append(bar)
            except Exception as exc:
                logger.warning(
                    "MassiveDataSource: skipping malformed bar %s: %s", r, exc
                )

        return sorted(bars, key=lambda b: b.timestamp)

    async def get_rsi(self, ticker: str, window: int = 14) -> float | None:
        """
        Fetch pre-computed RSI from Massive.

        Returns the most-recent RSI value as a float, or ``None`` if unavailable.
        """
        try:
            result = await self._client.get_rsi(ticker, timespan="day", window=window)
            # result is {"values": [{"timestamp": ..., "value": 62.3}], ...}
            values = result.get("values") or []
            if values:
                return float(values[0]["value"])
        except Exception as exc:
            logger.warning("MassiveDataSource.get_rsi failed for %s: %s", ticker, exc)
        return None
