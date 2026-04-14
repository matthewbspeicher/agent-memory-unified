"""WeightSetter — sets on-chain weights for Bittensor Subnet 8 validator.

Periodically reads miner rankings from the store and submits weight updates
to the chain via subtensor.set_weights(). Without this, the validator earns
no incentive and risks deregistration.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from integrations.bittensor.models import BittensorMetrics
from storage.bittensor import BittensorStore

logger = logging.getLogger(__name__)


# Canonical skip reasons — add new values here rather than ad-hoc strings so
# dashboards can enumerate known states.
SKIP_INSUFFICIENT_RANKINGS = "insufficient_rankings"
SKIP_ZERO_SCORE = "zero_score"
SKIP_NO_METAGRAPH = "no_metagraph"
SKIP_NO_MATCHING_UIDS = "no_matching_uids"
FAIL_CHAIN_ERROR = "chain_error"
FAIL_CHAIN_RETURNED_FALSE = "chain_returned_false"


class WeightSetter:
    """Sets on-chain weights based on miner rankings."""

    def __init__(
        self,
        adapter: Any,  # TaoshiProtocolAdapter
        store: BittensorStore,
        netuid: int,
        wallet: Any,  # bt.Wallet
        subtensor: Any,  # bt.Subtensor
        set_interval: float = 300.0,  # 5 minutes
        min_rankings: int = 1,
        version_key: int = 1,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._netuid = netuid
        self._wallet = wallet
        self._subtensor = subtensor
        self._set_interval = set_interval
        self._min_rankings = min_rankings
        self._version_key = version_key
        self._running = False
        self._metrics = BittensorMetrics()

    @property
    def metrics(self) -> BittensorMetrics:
        return self._metrics

    async def run(self) -> None:
        """Periodic weight-setting loop."""
        self._running = True
        logger.info(
            "WeightSetter started (netuid=%d, interval=%.1fs)",
            self._netuid,
            self._set_interval,
        )
        while self._running:
            try:
                await self._set_weights_once()
            except Exception as exc:
                self._metrics.weight_sets_failed += 1
                self._metrics.last_weight_skip_reason = FAIL_CHAIN_ERROR
                await self._log_attempt(
                    status="failed",
                    skip_reason=FAIL_CHAIN_ERROR,
                    uid_count=0,
                    weights_payload=None,
                    block=None,
                    error_detail=str(exc),
                )
                logger.error("WeightSetter error: %s", exc, exc_info=True)
            await asyncio.sleep(self._set_interval)
        logger.info("WeightSetter stopped")

    def stop(self) -> None:
        self._running = False

    async def _record_skip(self, reason: str, uid_count: int = 0) -> None:
        """Bump skip counters, remember the reason, persist an audit row."""
        self._metrics.weight_sets_skipped += 1
        self._metrics.last_weight_skip_reason = reason
        await self._log_attempt(
            status="skipped",
            skip_reason=reason,
            uid_count=uid_count,
            weights_payload=None,
            block=None,
            error_detail=None,
        )

    async def _log_attempt(
        self,
        *,
        status: str,
        skip_reason: str | None,
        uid_count: int,
        weights_payload: list[tuple[int, float]] | None,
        block: int | None,
        error_detail: str | None,
    ) -> None:
        """Persist a weight-set attempt. Non-fatal on storage failure — we
        never want the audit log to break the setter loop."""
        save = getattr(self._store, "save_weight_set_log", None)
        if save is None:
            return  # Older store without audit support — skip silently.
        try:
            await save(
                attempted_at=datetime.now(timezone.utc),
                status=status,
                skip_reason=skip_reason,
                uid_count=uid_count,
                weights_payload=weights_payload,
                block=block,
                error_detail=error_detail,
            )
        except Exception as exc:
            logger.warning("WeightSetter: audit log write failed: %s", exc)

    async def _set_weights_once(self) -> None:
        """Fetch rankings and submit weight transaction."""
        rankings = await self._store.get_miner_rankings(limit=256, symbol="aggregate")
        if len(rankings) < self._min_rankings:
            logger.warning(
                "WeightSetter: insufficient rankings (%d < %d), skipping",
                len(rankings),
                self._min_rankings,
            )
            await self._record_skip(SKIP_INSUFFICIENT_RANKINGS, uid_count=len(rankings))
            return

        total_score = sum(r.hybrid_score for r in rankings)
        if total_score <= 0:
            logger.warning("WeightSetter: total hybrid_score is zero, skipping")
            await self._record_skip(SKIP_ZERO_SCORE, uid_count=len(rankings))
            return

        metagraph = self._adapter.metagraph
        if metagraph is None:
            logger.warning("WeightSetter: metagraph not loaded, skipping")
            await self._record_skip(SKIP_NO_METAGRAPH)
            return

        uids: list[int] = []
        weights: list[float] = []
        hotkey_to_uid = {hk: i for i, hk in enumerate(metagraph.hotkeys)}
        for ranking in rankings:
            uid = hotkey_to_uid.get(ranking.miner_hotkey)
            if uid is None:
                logger.debug(
                    "WeightSetter: hotkey %s not in metagraph, skipping",
                    ranking.miner_hotkey[:12],
                )
                continue
            weight = ranking.hybrid_score / total_score
            uids.append(uid)
            weights.append(weight)

        if not uids:
            logger.warning("WeightSetter: no matching UIDs found in metagraph")
            await self._record_skip(SKIP_NO_MATCHING_UIDS)
            return

        try:
            logger.info(
                "WeightSetter: setting weights for %d miners (netuid=%d)",
                len(uids),
                self._netuid,
            )
            success = await asyncio.to_thread(
                self._subtensor.set_weights,
                wallet=self._wallet,
                netuid=self._netuid,
                uids=uids,
                weights=weights,
                version_key=self._version_key,
                wait_for_inclusion=False,  # async fire-and-forget
                wait_for_finalization=False,
            )
            block = getattr(self._subtensor, "block", None)
            payload = list(zip(uids, weights))
            if success:
                self._metrics.weight_sets_total += 1
                self._metrics.last_weight_set_block = block
                self._metrics.last_weight_set_at = datetime.now(timezone.utc)
                self._metrics.last_weight_set_uid_count = len(uids)
                await self._log_attempt(
                    status="success",
                    skip_reason=None,
                    uid_count=len(uids),
                    weights_payload=payload,
                    block=block,
                    error_detail=None,
                )
                logger.info("WeightSetter: weights set successfully")
            else:
                self._metrics.weight_sets_failed += 1
                self._metrics.last_weight_skip_reason = FAIL_CHAIN_RETURNED_FALSE
                await self._log_attempt(
                    status="failed",
                    skip_reason=FAIL_CHAIN_RETURNED_FALSE,
                    uid_count=len(uids),
                    weights_payload=payload,
                    block=block,
                    error_detail=None,
                )
                logger.warning("WeightSetter: set_weights returned False")
        except Exception as exc:
            self._metrics.weight_sets_failed += 1
            self._metrics.last_weight_skip_reason = FAIL_CHAIN_ERROR
            await self._log_attempt(
                status="failed",
                skip_reason=FAIL_CHAIN_ERROR,
                uid_count=len(uids),
                weights_payload=list(zip(uids, weights)),
                block=None,
                error_detail=str(exc),
            )
            logger.error("WeightSetter: failed to set weights: %s", exc)
