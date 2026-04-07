from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from integrations.bittensor.adapter import FORWARD_DELAY_SECONDS, HASH_WINDOWS
from integrations.bittensor.derivation import derive_consensus_view
from integrations.bittensor.models import BittensorMetrics

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setLevel(logging.DEBUG)
    _h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(_h)


def next_hash_window(now: datetime) -> datetime:
    """Return the next hash window boundary (minute 0 or 30).

    Always returns a strictly future boundary to prevent immediate re-collection
    when the scheduler overruns a window.
    """
    boundaries = sorted(HASH_WINDOWS)  # (0, 30)

    for boundary in boundaries:
        candidate = now.replace(minute=boundary, second=0, microsecond=0)
        if candidate > now:
            return candidate

    # Past all boundaries in this hour — advance to next hour, minute 0
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return next_hour


class TaoshiScheduler:
    """Runs the Taoshi collection loop, aligned to hash-window boundaries."""

    supports_collection = True

    def __init__(
        self,
        adapter: Any,
        store: Any,
        event_bus: Any,
        signal_bus: Any = None,
        selection_policy: str = "top_n",
        selection_metric: str = "incentive",
        top_miners: int = 10,
        derivation_version: str = "v1",
        metrics: BittensorMetrics | None = None,
        streams: list[str] | None = None,
        direct_query_enabled: bool = False,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._event_bus = event_bus
        self._signal_bus = signal_bus
        self._selection_policy = selection_policy
        self._selection_metric = selection_metric
        self._top_miners = top_miners
        self._derivation_version = derivation_version
        self._streams = streams or ["BTCUSD-5m"]
        self._direct_query_enabled = direct_query_enabled
        self._running = False
        self.last_success_at: datetime | None = None
        self.windows_collected_total: int = 0
        self.last_window_responder_count: int = 0
        self.last_window_miner_count: int = 0
        self.metrics = metrics or BittensorMetrics()
        self._collection_durations: list[float] = []

    def select_miners(self, metagraph: Any) -> list[tuple[int, Any]]:
        """Return (uid, axon) pairs according to the configured selection policy.

        Supported policies:
        - "all"   — every neuron in the metagraph
        - "top_n" — top *_top_miners* neurons ranked by *_selection_metric*
        """
        uids: list[int] = list(metagraph.uids)
        axons: list[Any] = list(metagraph.axons)

        if self._selection_policy == "all":
            # Filter out miners with no advertised endpoint or IPv6 (often unreachable)
            return [
                (uid, axon)
                for uid, axon in zip(uids, axons)
                if getattr(axon, "ip", "0.0.0.0") != "0.0.0.0"
                and getattr(axon, "port", 0) != 0
                and ":" not in getattr(axon, "ip", "")
            ]

        # top_n: rank by the chosen metric
        if self._selection_metric == "incentive":
            scores: list[float] = list(metagraph.I)
        else:
            # Fallback — equal weight
            scores = [1.0] * len(uids)

        ranked = sorted(zip(uids, axons, scores), key=lambda t: t[2], reverse=True)
        top = ranked[: self._top_miners]
        return [(uid, axon) for uid, axon, _ in top]

    async def _wait_for_next_window(self) -> None:
        """Sleep until the next hash window boundary."""
        now = datetime.now(tz=timezone.utc)
        target = next_hash_window(now)
        delay = (target - now).total_seconds()
        if delay > 0:
            logger.debug(
                "Sleeping %.1f seconds until hash window at %s",
                delay,
                target.isoformat(),
            )
            await asyncio.sleep(delay)

    async def _collect_window(self, stream_id: str = "BTCUSD-5m") -> None:
        """Collect miner predictions for the current window via hash/forward cycle."""
        start_time = datetime.now(tz=timezone.utc)
        window_id = start_time.strftime("%Y%m%d-%H%M")
        request_uuid = str(uuid.uuid4())
        logger.info(
            "TaoshiScheduler: collecting window %s stream %s", window_id, stream_id
        )

        try:
            # Step 1: refresh metagraph
            await self._adapter.refresh_metagraph()

            # Step 2: select miners
            selected = self.select_miners(self._adapter.metagraph)
            uids = [uid for uid, _ in selected]
            axons = [axon for _, axon in selected]
            self.last_window_miner_count = len(selected)

            # Step 3: build request
            request = self._adapter.build_request(stream_id=stream_id)

            # Step 4: hash phase
            await self._event_bus.publish(
                "bittensor.window_started",
                {"window_id": window_id, "timestamp": start_time.isoformat()},
            )
            hash_forecasts = await self._adapter.query_miners(
                axons, uids, request, window_id, f"{request_uuid}-hash"
            )

            # Step 5: forward delay
            elapsed = (datetime.now(tz=timezone.utc) - start_time).total_seconds()
            delay = max(0, FORWARD_DELAY_SECONDS - elapsed)
            if elapsed > 45:
                logger.warning(
                    "Hash phase took %.1f seconds (>45s), forward delay reduced to %.1f",
                    elapsed,
                    delay,
                )
            await asyncio.sleep(delay)

            # Step 6: forward phase
            forward_forecasts = await self._adapter.query_miners(
                axons, uids, request, window_id, f"{request_uuid}-fwd"
            )

            # Step 7: hash verification
            hash_by_hotkey = {f.miner_hotkey: f for f in hash_forecasts}
            for forecast in forward_forecasts:
                hash_forecast = hash_by_hotkey.get(forecast.miner_hotkey)
                if hash_forecast is not None:
                    verified = self._adapter.verify_hash_commitment(
                        hash_forecast.hashed_predictions, forecast.predictions
                    )
                else:
                    verified = False
                if verified:
                    self.metrics.hash_verifications_passed += 1
                else:
                    self.metrics.hash_verifications_failed += 1
                try:
                    forecast.hash_verified = verified
                except Exception:
                    object.__setattr__(forecast, "hash_verified", verified)

            # Step 8: persist raw forecasts
            await self._store.save_raw_forecasts(hash_forecasts + forward_forecasts)

            # Step 9: derive consensus view
            verified_forecasts = [f for f in forward_forecasts if f.hash_verified]
            symbol, timeframe = self._adapter.parse_stream_id(request.stream_id)
            view = derive_consensus_view(
                verified_forecasts,
                window_id,
                symbol,
                timeframe,
                str(self._derivation_version),
            )

            # Step 10: persist derived view
            await self._store.save_derived_view(view)

            # Step 11: publish event and update counters
            self.last_window_responder_count = len(forward_forecasts)
            self.windows_collected_total += 1
            self.last_success_at = datetime.now(tz=timezone.utc)

            # Metrics
            duration = (datetime.now(tz=timezone.utc) - start_time).total_seconds()
            self.metrics.windows_collected += 1
            self.metrics.last_collection_duration_secs = duration
            self._collection_durations.append(duration)
            if len(self._collection_durations) > 100:
                self._collection_durations = self._collection_durations[-100:]
            self.metrics.avg_collection_duration_secs = (
                sum(self._collection_durations) / len(self._collection_durations)
            )
            self.metrics.last_miner_response_rate = (
                len(forward_forecasts) / self.last_window_miner_count
                if self.last_window_miner_count > 0
                else 0.0
            )
            self.metrics.consecutive_failures = 0

            await self._event_bus.publish(
                "bittensor.window_collected",
                {
                    "window_id": window_id,
                    "miner_count": self.last_window_miner_count,
                    "responder_count": self.last_window_responder_count,
                    "verified_count": len(verified_forecasts),
                    "symbol": symbol,
                    "timeframe": timeframe,
                },
            )

            # --- Bridge to SignalBus (Track 17b) ---
            try:
                from integrations.bittensor.signals import (
                    BittensorSignalPayload,
                    create_bittensor_agent_signal,
                )

                # Map consensus direction score to string
                direction = "flat"
                if view.weighted_direction > 0.3:
                    direction = "bullish"
                elif view.weighted_direction < -0.3:
                    direction = "bearish"

                payload = BittensorSignalPayload(
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=direction,
                    confidence=view.agreement_ratio,
                    expected_return=view.weighted_expected_return,
                    window_id=window_id,
                    miner_count=len(verified_forecasts),
                )

                # We need a reference to the signal_bus.
                # For now, we'll try to get it from the app state if possible,
                # but better to inject it in __init__.
                if hasattr(self, "_signal_bus") and self._signal_bus:
                    signal = create_bittensor_agent_signal(payload)
                    await self._signal_bus.publish(signal)
            except Exception as sig_exc:
                logger.error("Failed to publish to SignalBus: %s", sig_exc)

            logger.info(
                "Window %s collected: %d miners, %d responders, %d verified",
                window_id,
                self.last_window_miner_count,
                self.last_window_responder_count,
                len(verified_forecasts),
            )

        except Exception as exc:
            self.metrics.windows_failed += 1
            self.metrics.consecutive_failures += 1
            logger.exception("TaoshiScheduler: window %s failed: %s", window_id, exc)
            await self._event_bus.publish(
                "bittensor.window_failed",
                {"window_id": window_id, "error": str(exc)},
            )

    async def _try_reconnect(self) -> bool:
        """Attempt to reconnect the adapter after consecutive failures."""
        logger.warning(
            "TaoshiScheduler: %d consecutive failures, attempting reconnect",
            self.metrics.consecutive_failures,
        )
        try:
            await self._adapter.connect(max_retries=3, retry_delay=5.0)
            await self._adapter.refresh_metagraph()
            self.metrics.consecutive_failures = 0
            self.metrics.metagraph_refreshes += 1
            logger.info("TaoshiScheduler: reconnect succeeded")
            return True
        except Exception as exc:
            self.metrics.connection_failures += 1
            self.metrics.last_connection_failure_at = datetime.now(tz=timezone.utc)
            logger.error("TaoshiScheduler: reconnect failed: %s", exc)
            return False

    async def run(self) -> None:
        """Main collection loop. Runs until stop() is called or task is cancelled."""
        self._running = True
        if not self._direct_query_enabled:
            logger.info(
                "TaoshiScheduler: direct dendrite queries disabled "
                "(STA_BITTENSOR_DIRECT_QUERY_ENABLED=false). "
                "Miner data flows through TaoshiBridge instead."
            )
            return
        logger.info("TaoshiScheduler started (direct dendrite queries enabled)")
        try:
            while self._running:
                # Circuit breaker: reconnect after 3 consecutive failures
                if self.metrics.consecutive_failures >= 3:
                    reconnected = await self._try_reconnect()
                    if not reconnected:
                        backoff = min(
                            60 * (2 ** (self.metrics.consecutive_failures - 3)), 1800
                        )
                        logger.warning(
                            "TaoshiScheduler: backing off %.0f seconds after reconnect failure",
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue

                await self._wait_for_next_window()
                if not self._running:
                    break
                for stream_id in self._streams:
                    if not self._running:
                        break
                    await self._collect_window(stream_id=stream_id)
        except asyncio.CancelledError:
            logger.info("TaoshiScheduler cancelled")
        finally:
            self._running = False
            logger.info("TaoshiScheduler stopped")

    def stop(self) -> None:
        """Signal the run loop to exit after the current collection finishes."""
        self._running = False
