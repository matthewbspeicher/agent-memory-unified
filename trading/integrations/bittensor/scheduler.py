from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from integrations.bittensor.adapter import FORWARD_DELAY_SECONDS, HASH_WINDOWS
from integrations.bittensor.derivation import derive_consensus_view

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._event_bus = event_bus
        self._signal_bus = signal_bus
        self._selection_policy = selection_policy
        self._selection_metric = selection_metric
        self._top_miners = top_miners
        self._derivation_version = derivation_version
        self._running = False
        self.last_success_at: datetime | None = None
        self.windows_collected_total: int = 0
        self.last_window_responder_count: int = 0
        self.last_window_miner_count: int = 0

    def select_miners(self, metagraph: Any) -> list[tuple[int, Any]]:
        """Return (uid, axon) pairs according to the configured selection policy.

        Supported policies:
        - "all"   — every neuron in the metagraph
        - "top_n" — top *_top_miners* neurons ranked by *_selection_metric*
        """
        uids: list[int] = list(metagraph.uids)
        axons: list[Any] = list(metagraph.axons)

        if self._selection_policy == "all":
            return list(zip(uids, axons))

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

    async def _collect_window(self) -> None:
        """Collect miner predictions for the current window via hash/forward cycle."""
        start_time = datetime.now(tz=timezone.utc)
        window_id = start_time.strftime("%Y%m%d-%H%M")
        request_uuid = str(uuid.uuid4())
        logger.info("TaoshiScheduler: collecting window %s", window_id)

        try:
            # Step 1: refresh metagraph
            await self._adapter.refresh_metagraph()

            # Step 2: select miners
            selected = self.select_miners(self._adapter.metagraph)
            uids = [uid for uid, _ in selected]
            axons = [axon for _, axon in selected]
            self.last_window_miner_count = len(selected)

            # Step 3: build request
            request = self._adapter.build_request()

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
            logger.exception("TaoshiScheduler: window %s failed: %s", window_id, exc)
            await self._event_bus.publish(
                "bittensor.window_failed",
                {"window_id": window_id, "error": str(exc)},
            )

    async def run(self) -> None:
        """Main collection loop. Runs until stop() is called or task is cancelled."""
        self._running = True
        logger.info("TaoshiScheduler started")
        try:
            while self._running:
                await self._wait_for_next_window()
                if not self._running:
                    break
                await self._collect_window()
        except asyncio.CancelledError:
            logger.info("TaoshiScheduler cancelled")
        finally:
            self._running = False
            logger.info("TaoshiScheduler stopped")

    def stop(self) -> None:
        """Signal the run loop to exit after the current collection finishes."""
        self._running = False
