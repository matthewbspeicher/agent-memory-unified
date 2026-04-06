from __future__ import annotations
import logging

from broker.models import Quote, Symbol
from data.bus import DataBus
from data.events import EventBus
from streaming.base import BrokerStream

logger = logging.getLogger(__name__)


class StreamManager:
    """Manages subscriptions across multiple broker streams with dedup and fan-out."""

    def __init__(
        self,
        streams: dict[str, BrokerStream],
        data_bus: DataBus,
        event_bus: EventBus,
    ) -> None:
        self._streams = streams
        self._data_bus = data_bus
        self._event_bus = event_bus
        self._symbol_to_broker: dict[str, str] = {}  # symbol → broker_name (one stream per symbol)

    async def subscribe(self, symbols: list[str], broker: str | None = None) -> None:
        """Subscribe to symbols. One stream per symbol — first subscriber wins."""
        if broker and broker not in self._streams:
            logger.warning("Stream '%s' not available, skipping subscribe", broker)
            return

        # Filter to symbols not already subscribed
        new_symbols = [s for s in symbols if s not in self._symbol_to_broker]
        if not new_symbols:
            return

        # Pick the stream
        if broker:
            stream = self._streams[broker]
            stream_name = broker
        else:
            # Use first available
            stream_name, stream = next(iter(self._streams.items()))

        await stream.subscribe(new_symbols)
        for s in new_symbols:
            self._symbol_to_broker[s] = stream_name
        logger.info("Subscribed %d symbols on %s: %s", len(new_symbols), stream_name, new_symbols)

    async def unsubscribe(self, symbols: list[str]) -> None:
        by_broker: dict[str, list[str]] = {}
        for s in symbols:
            broker = self._symbol_to_broker.pop(s, None)
            if broker:
                by_broker.setdefault(broker, []).append(s)
        for broker_name, syms in by_broker.items():
            await self._streams[broker_name].unsubscribe(syms)

    async def start(self) -> None:
        """Connect all streams and register fan-out callbacks."""
        for name, stream in self._streams.items():
            stream.on_quote(self._on_quote)
            stream.on_disconnected(lambda broker_name=name: self._on_stream_disconnected(broker_name))
            try:
                await stream.connect()
                await self._event_bus.publish("stream.connected", {"broker": name})
                logger.info("Stream '%s' connected", name)
            except Exception as e:
                logger.warning("Stream '%s' failed to connect: %s", name, e)

    async def stop(self) -> None:
        """Disconnect all streams."""
        for name, stream in self._streams.items():
            try:
                await stream.disconnect()
            except Exception:
                pass

    async def _on_quote(self, symbol: str, quote: Quote) -> None:
        """Fan-out: update DataBus cache + publish to EventBus."""
        await self._data_bus.update_quote_cache(Symbol(ticker=symbol), quote)
        await self._event_bus.publish(f"quote.{symbol}", quote)

    def _on_stream_disconnected(self, broker_name: str) -> None:
        """Invalidate DataBus cache for symbols owned by disconnected stream."""
        affected = [s for s, b in self._symbol_to_broker.items() if b == broker_name]
        if affected:
            self._data_bus.invalidate_quote_cache(affected)
            logger.warning(
                "Stream '%s' disconnected — invalidated %d cached quotes",
                broker_name, len(affected),
            )
