"""SignalFeatureCapture — derives and persists signal-time features for every routed opportunity.

Design principles:
- One fetch per symbol: bars are fetched once and reused for all indicator computations.
- Best-effort: any individual computation failure yields a null, never aborts capture.
- Non-blocking: called via asyncio.create_task() from OpportunityRouter.route().
- Idempotent: uses SignalFeatureStore.upsert() so retries are safe.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from data.indicators import (
    compute_atr,
    compute_bollinger,
    compute_ema,
    compute_macd,
    compute_realized_vol,
    compute_relative_volume,
    compute_rsi,
    compute_sma,
)

if TYPE_CHECKING:
    from agents.models import ActionLevel, Opportunity
    from data.bus import DataBus
    from storage.signal_features import SignalFeatureStore

logger = logging.getLogger(__name__)

FEATURE_VERSION = "1.0"
MARKET_PROXY = "SPY"


class SignalFeatureCapture:
    """Captures and persists a signal-time feature row for a routed opportunity."""

    def __init__(
        self, store: "SignalFeatureStore", data_bus: "DataBus | None" = None
    ) -> None:
        self._store = store
        self._data_bus = data_bus

    async def capture(
        self,
        opportunity: "Opportunity",
        action_level: "ActionLevel | None" = None,
    ) -> None:
        """Derive and persist a feature row. Best-effort — never raises to the caller."""
        t_start = time.monotonic()
        try:
            await self._do_capture(opportunity, action_level, t_start)
        except Exception as exc:
            logger.warning(
                "SignalFeatureCapture failed for opportunity %s (non-fatal): %s",
                opportunity.id,
                exc,
            )
            # Store a minimal failed row so the opportunity is traceable
            try:
                await self._store.upsert(
                    str(opportunity.id),
                    agent_name=opportunity.agent_name,
                    symbol=opportunity.symbol.ticker,
                    signal=opportunity.signal,
                    asset_type=opportunity.symbol.asset_type.value,
                    broker_id=opportunity.broker_id,
                    confidence=float(opportunity.confidence),
                    opportunity_timestamp=opportunity.timestamp.isoformat(),
                    captured_at=datetime.now(timezone.utc).isoformat(),
                    feature_version=FEATURE_VERSION,
                    feature_payload="{}",
                    capture_status="failed",
                    capture_error=str(exc)[:500],
                )
            except Exception as store_exc:
                logger.warning(
                    "SignalFeatureCapture could not write failed row for %s: %s",
                    opportunity.id,
                    store_exc,
                )

    async def _do_capture(
        self,
        opportunity: "Opportunity",
        action_level: "ActionLevel | None",
        t_start: float,
    ) -> None:
        from broker.models import Symbol, AssetType

        captured_at = datetime.now(timezone.utc)
        opp_ts = opportunity.timestamp
        if not opp_ts.tzinfo:
            opp_ts = opp_ts.replace(tzinfo=timezone.utc)
        capture_delay_ms = (captured_at - opp_ts).total_seconds() * 1000

        features: dict[str, Any] = {
            "agent_name": opportunity.agent_name,
            "symbol": opportunity.symbol.ticker,
            "signal": opportunity.signal,
            "asset_type": opportunity.symbol.asset_type.value,
            "broker_id": opportunity.broker_id,
            "confidence": float(opportunity.confidence),
            "opportunity_timestamp": opp_ts.isoformat(),
            "captured_at": captured_at.isoformat(),
            "capture_delay_ms": round(capture_delay_ms, 2),
            "feature_version": FEATURE_VERSION,
            "capture_status": "captured",
        }

        partial = False

        # --- Quote features ---
        if self._data_bus:
            try:
                quote = await self._data_bus.get_quote(opportunity.symbol)
                if quote:
                    bid = float(quote.bid) if quote.bid else None
                    ask = float(quote.ask) if quote.ask else None
                    last = float(quote.last) if quote.last else None
                    mid = None
                    if bid is not None and ask is not None:
                        mid = (bid + ask) / 2
                    elif last is not None:
                        mid = last
                    spread_bps = None
                    if bid is not None and ask is not None and mid and mid > 0:
                        spread_bps = ((ask - bid) / mid) * 10000
                    features["quote_bid"] = str(quote.bid) if quote.bid else None
                    features["quote_ask"] = str(quote.ask) if quote.ask else None
                    features["quote_last"] = str(quote.last) if quote.last else None
                    features["quote_mid"] = (
                        str(round(mid, 6)) if mid is not None else None
                    )
                    features["spread_bps"] = (
                        round(spread_bps, 4) if spread_bps is not None else None
                    )
            except Exception as exc:
                logger.debug(
                    "Quote fetch failed for %s: %s", opportunity.symbol.ticker, exc
                )
                partial = True

        # --- Technical indicators from historical bars ---
        bars = None
        if self._data_bus:
            try:
                bars = await self._data_bus.get_historical(
                    opportunity.symbol, timeframe="1d", period="3mo"
                )
            except Exception as exc:
                logger.debug(
                    "Historical fetch failed for %s: %s", opportunity.symbol.ticker, exc
                )
                partial = True

        if bars:
            # RSI(14)
            _try_set(features, "rsi_14", compute_rsi, bars, 14)
            # SMA(20)
            _try_set(features, "sma_20", compute_sma, bars, 20)
            # EMA(20)
            _try_set(features, "ema_20", compute_ema, bars, 20)
            # MACD
            try:
                macd = compute_macd(bars)
                features["macd_line"] = round(macd.macd_line, 6)
                features["macd_signal"] = round(macd.signal_line, 6)
                features["macd_histogram"] = round(macd.histogram, 6)
            except Exception:
                partial = True
            # Bollinger Bands
            try:
                bb = compute_bollinger(bars, period=20)
                features["bollinger_upper"] = round(bb.upper, 6)
                features["bollinger_middle"] = round(bb.middle, 6)
                features["bollinger_lower"] = round(bb.lower, 6)
                # %B = (close - lower) / (upper - lower)
                close = float(bars[-1].close)
                band_range = bb.upper - bb.lower
                if band_range > 0:
                    features["bollinger_pct_b"] = round(
                        (close - bb.lower) / band_range, 6
                    )
            except Exception:
                partial = True
            # ATR(14)
            _try_set(features, "atr_14", compute_atr, bars, 14)
            # Realized vol (20d)
            _try_set(features, "realized_vol_20d", compute_realized_vol, bars, 20)
            # Relative volume (20d)
            _try_set(features, "relative_volume_20d", compute_relative_volume, bars, 20)
            # Distance to SMA20 / EMA20 as percent
            close = float(bars[-1].close)
            if "sma_20" in features and features["sma_20"] and features["sma_20"] > 0:
                features["distance_to_sma20_pct"] = round(
                    (close - features["sma_20"]) / features["sma_20"] * 100, 4
                )
            if "ema_20" in features and features["ema_20"] and features["ema_20"] > 0:
                features["distance_to_ema20_pct"] = round(
                    (close - features["ema_20"]) / features["ema_20"] * 100, 4
                )

        # --- Regime fields from opportunity.data ---
        regime = opportunity.data.get("regime") or {}
        if regime:
            features["trend_regime"] = regime.get("trend_regime")
            features["volatility_regime"] = regime.get("volatility_regime")
            features["liquidity_regime"] = regime.get("liquidity_regime")
            features["event_regime"] = regime.get("event_regime")
            features["market_state"] = regime.get("market_state")

        # --- Market proxy context (SPY) for equity assets ---

        if (
            self._data_bus
            and opportunity.symbol.asset_type in (AssetType.STOCK, AssetType.OPTION)
            and opportunity.symbol.ticker != MARKET_PROXY
        ):
            try:
                proxy_sym = Symbol(ticker=MARKET_PROXY, asset_type=AssetType.STOCK)
                proxy_bars = await self._data_bus.get_historical(
                    proxy_sym, timeframe="1d", period="3mo"
                )
                if proxy_bars and len(proxy_bars) >= 2:
                    features["market_proxy_symbol"] = MARKET_PROXY
                    _try_set(
                        features, "market_proxy_rsi_14", compute_rsi, proxy_bars, 14
                    )
                    # 1-day return: (last / prev_close - 1)
                    last_close = float(proxy_bars[-1].close)
                    prev_close = float(proxy_bars[-2].close)
                    if prev_close > 0:
                        features["market_proxy_return_1d"] = round(
                            (last_close / prev_close - 1) * 100, 4
                        )
            except Exception as exc:
                logger.debug("Market proxy fetch failed: %s", exc)
                partial = True

        # --- Build feature_payload from agent extras + action_level ---
        payload: dict[str, Any] = {}
        agent_extras = opportunity.data.get("signal_features")
        if isinstance(agent_extras, dict):
            payload.update(agent_extras)
        if opportunity.suggested_trade is not None:
            try:
                from execution.costs import order_type_label

                payload.setdefault(
                    "order_type", order_type_label(opportunity.suggested_trade)
                )
            except Exception:
                pass
        if action_level is not None:
            payload["action_level"] = action_level.value
        features["feature_payload"] = json.dumps(payload)

        if partial:
            features["capture_status"] = "partial"

        await self._store.upsert(str(opportunity.id), **features)
        logger.debug(
            "SignalFeatureCapture: persisted %s features for %s (%s)",
            features["capture_status"],
            opportunity.id,
            opportunity.symbol.ticker,
        )


def _try_set(
    features: dict[str, Any],
    key: str,
    fn: Any,
    *args: Any,
) -> None:
    """Call fn(*args), round to 6 decimals, and store in features[key].

    On any exception, leaves key absent (null in DB).
    """
    try:
        val = fn(*args)
        features[key] = round(float(val), 6)
    except Exception:
        pass
