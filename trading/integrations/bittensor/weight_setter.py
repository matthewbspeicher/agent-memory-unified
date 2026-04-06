from __future__ import annotations

import asyncio
import logging
from typing import Any

from integrations.bittensor.models import BittensorMetrics, MinerRanking

logger = logging.getLogger(__name__)


class WeightSetter:
    """Periodically sets on-chain weights based on miner rankings.

    Validators must call subtensor.set_weights() to score miners.
    This determines miner incentive distribution and validator rewards.
    """

    def __init__(
        self,
        adapter: Any,
        store: Any,
        netuid: int = 8,
        interval_blocks: int = 100,
        min_rankings: int = 5,
        metrics: BittensorMetrics | None = None,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._netuid = netuid
        self._interval_blocks = interval_blocks
        self._min_rankings = min_rankings
        self._running = False
        self.last_set_at_block: int | None = None
        self.total_weight_sets: int = 0
        self.metrics = metrics or BittensorMetrics()

    def compute_weight_vector(
        self,
        rankings: list[MinerRanking],
        hotkey_to_uid: dict[str, int],
    ) -> tuple[list[int], list[float]]:
        """Convert miner rankings to normalized (uids, weights) vectors.

        Maps hybrid_score to weights that sum to 1.0.
        Only includes miners present in both rankings and metagraph.
        """
        if not rankings:
            return [], []

        valid = [
            (hotkey_to_uid[r.miner_hotkey], r.hybrid_score)
            for r in rankings
            if r.miner_hotkey in hotkey_to_uid and r.hybrid_score > 0
        ]

        if not valid:
            return [], []

        uids = [uid for uid, _ in valid]
        scores = [score for _, score in valid]

        total = sum(scores)
        if total <= 0:
            return [], []

        weights = [s / total for s in scores]
        return uids, weights

    async def set_weights_once(self) -> bool:
        """Compute and set weights on-chain once."""
        metagraph = self._adapter.metagraph
        if metagraph is None:
            logger.warning("WeightSetter: metagraph not loaded, skipping")
            return False

        hotkey_to_uid: dict[str, int] = {
            hk: uid for uid, hk in zip(metagraph.uids, metagraph.hotkeys)
        }

        rankings = await self._store.get_miner_rankings(limit=256)
        if len(rankings) < self._min_rankings:
            logger.info(
                "WeightSetter: only %d rankings (min %d), skipping",
                len(rankings),
                self._min_rankings,
            )
            return False

        uids, weights = self.compute_weight_vector(rankings, hotkey_to_uid)
        if not uids:
            logger.warning("WeightSetter: no valid weights to set")
            return False

        subtensor = self._adapter._subtensor
        wallet = self._adapter._wallet
        if subtensor is None or wallet is None:
            logger.error("WeightSetter: subtensor or wallet not initialized")
            return False

        try:
            success, msg = subtensor.set_weights(
                netuid=self._netuid,
                wallet=wallet,
                uids=uids,
                weights=weights,
                wait_for_inclusion=True,
            )
            if success:
                block = getattr(metagraph, "block", None)
                self.last_set_at_block = block
                self.total_weight_sets += 1
                self.metrics.weight_sets_total += 1
                self.metrics.last_weight_set_block = block
                logger.info(
                    "WeightSetter: set weights for %d miners at block %s (total sets: %d)",
                    len(uids),
                    block,
                    self.total_weight_sets,
                )
            else:
                self.metrics.weight_sets_failed += 1
                logger.warning("WeightSetter: set_weights returned failure: %s", msg)
            return success
        except Exception as exc:
            self.metrics.weight_sets_failed += 1
            logger.exception("WeightSetter: set_weights failed: %s", exc)
            return False

    async def run(self) -> None:
        """Background loop: set weights every interval_blocks (~20 min at 12s/block)."""
        self._running = True
        interval_secs = self._interval_blocks * 12
        consecutive_failures = 0
        logger.info(
            "WeightSetter started (interval=%d blocks / %d secs, netuid=%d)",
            self._interval_blocks,
            interval_secs,
            self._netuid,
        )
        try:
            while self._running:
                try:
                    await self._adapter.refresh_metagraph()
                    success = await self.set_weights_once()
                    if success:
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                except Exception as exc:
                    consecutive_failures += 1
                    self.metrics.connection_failures += 1
                    logger.error(
                        "WeightSetter: cycle failed (%d consecutive): %s",
                        consecutive_failures,
                        exc,
                    )
                    if consecutive_failures >= 3:
                        backoff = min(60 * (2 ** (consecutive_failures - 3)), 1800)
                        logger.warning(
                            "WeightSetter: backing off %.0f seconds", backoff
                        )
                        await asyncio.sleep(backoff)
                        continue
                await asyncio.sleep(interval_secs)
        except asyncio.CancelledError:
            logger.info("WeightSetter cancelled")
        finally:
            self._running = False
            logger.info("WeightSetter stopped")

    def stop(self) -> None:
        self._running = False
