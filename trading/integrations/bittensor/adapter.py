from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import math
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from integrations.bittensor.models import PredictionRequest, RawMinerForecast

logger = logging.getLogger(__name__)

# Protocol timing constants (UTC minute boundaries)
HASH_WINDOWS = (0, 30)
FORWARD_WINDOWS = (1, 2, 3, 31, 32, 33)
METAGRAPH_REFRESH_WINDOWS = (25, 55)

# Default request template
DEFAULT_STREAM_ID = "BTCUSD-5m"
DEFAULT_TOPIC_ID = 1
DEFAULT_SCHEMA_ID = 1
DEFAULT_FEATURE_IDS = [1, 2, 3, 4, 5]
DEFAULT_PREDICTION_SIZE = 100
FORWARD_DELAY_SECONDS = 60


class TaoshiProtocolAdapter:
    """Encapsulates all Bittensor/Taoshi protocol details.

    Owns subtensor connection, metagraph access, synapse building,
    and validation. Nothing outside this module should import bittensor SDK classes.
    """

    def __init__(
        self,
        network: str,
        endpoint: str,
        wallet_name: str,
        hotkey_path: str,
        hotkey: str,
        subnet_uid: int,
    ) -> None:
        self._network = network
        self._endpoint = endpoint
        self._wallet_name = wallet_name
        self._hotkey_path = hotkey_path
        self._hotkey = hotkey
        self._subnet_uid = subnet_uid
        self._subtensor = None
        self._wallet = None
        self._dendrite = None
        self._metagraph = None

    async def connect(self, max_retries: int = 5, retry_delay: float = 5.0) -> None:
        """Initialize subtensor connection, wallet, and dendrite with retry."""
        try:
            import bittensor as bt
        except ImportError:
            raise ImportError("bittensor SDK not installed. Run: pip install bittensor")

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                # bt.Subtensor / bt.Wallet / bt.Dendrite (v10+ capitalized)
                _Subtensor = getattr(bt, "Subtensor", None) or getattr(bt, "subtensor")
                _Wallet = getattr(bt, "Wallet", None) or getattr(bt, "wallet")
                _Dendrite = getattr(bt, "Dendrite", None) or getattr(bt, "dendrite")

                self._subtensor = _Subtensor(
                    network=self._network,
                )
                self._wallet = _Wallet(
                    name=self._wallet_name,
                    path=self._hotkey_path or None,
                    hotkey=self._hotkey,
                )
                self._dendrite = _Dendrite(wallet=self._wallet)
                logger.info(
                    "Bittensor adapter connected (network=%s, endpoint=%s, subnet=%d) on attempt %d",
                    self._network,
                    self._endpoint,
                    self._subnet_uid,
                    attempt,
                )
                return
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    delay = retry_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Bittensor connect attempt %d/%d failed: %s. Retrying in %.1fs",
                        attempt,
                        max_retries,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        raise last_exc or ConnectionError("Failed to connect after retries")

    async def refresh_metagraph(self) -> None:
        """Refresh the cached metagraph snapshot."""
        if self._subtensor is None:
            raise RuntimeError("Adapter not connected")
        self._metagraph = self._subtensor.metagraph(netuid=self._subnet_uid)
        logger.debug(
            "Metagraph refreshed: %d neurons, block %s",
            len(self._metagraph.uids) if self._metagraph else 0,
            getattr(self._metagraph, "block", "?"),
        )

    @property
    def metagraph(self):
        return self._metagraph

    @property
    def dendrite(self):
        return self._dendrite

    def is_hotkey_registered(self) -> bool:
        """Check if our hotkey is registered on the subnet."""
        if self._metagraph is None or self._wallet is None:
            return False
        hotkey_ss58 = self._wallet.hotkey.ss58_address
        return hotkey_ss58 in self._metagraph.hotkeys

    async def smoke_test(self) -> bool:
        """Check chain reachability and hotkey registration.

        This intentionally does not perform a dendrite capability probe yet.
        """
        try:
            await self.refresh_metagraph()
            if not self.is_hotkey_registered():
                logger.warning("Hotkey not registered on subnet %d", self._subnet_uid)
                return False
            logger.info("Bittensor smoke test passed")
            return True
        except Exception as e:
            logger.warning("Bittensor smoke test failed: %s", e)
            return False

    @staticmethod
    def parse_stream_id(stream_id: str) -> tuple[str, str]:
        """Parse 'BTCUSD-5m' into ('BTCUSD', '5m')."""
        parts = stream_id.rsplit("-", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid stream_id: {stream_id}")
        return parts[0], parts[1]

    @staticmethod
    def validate_tensor(predictions: list[float], expected_size: int) -> bool:
        """Validate a 1-D prediction tensor."""
        if len(predictions) != expected_size:
            return False
        for v in predictions:
            if not math.isfinite(v):
                return False
        return True

    def build_request(self, stream_id: str = DEFAULT_STREAM_ID) -> PredictionRequest:
        """Build a prediction request for a given stream."""
        return PredictionRequest(stream_id=stream_id)

    @staticmethod
    def _coerce_response_items(response: Any) -> list[Any]:
        if response is None:
            return []
        if isinstance(response, (list, tuple)):
            return list(response)
        return [response]

    @staticmethod
    def _safe_index(values: Any, index: int | None) -> Any | None:
        if index is None:
            return None
        if not values:
            return None
        try:
            return values[index]
        except Exception:
            return None

    def _build_query_payload(self, request: PredictionRequest) -> Any:
        """Build an object suitable for dendrite query dispatch."""
        try:
            import bittensor as bt  # type: ignore[import-not-found]

            synapse = bt.Synapse()
            for key, value in asdict(request).items():
                setattr(synapse, key, value)
            return synapse
        except Exception:
            return request

    async def _query_single_miner(
        self,
        uid: int,
        axon: Any,
        payload: Any,
        timeout: float,
    ) -> tuple[int, list[Any] | Any]:
        """Query a single miner through dendrite."""
        response = await self._dendrite(
            axons=[axon],
            synapse=payload,
            timeout=timeout,
        )
        return uid, self._coerce_response_items(response)

    async def query_miners(
        self,
        axons: list,
        uids: list[int],
        request: PredictionRequest,
        window_id: str,
        request_uuid: str,
        timeout: float = 12.0,
    ) -> list[RawMinerForecast]:
        """Query miners via dendrite. Returns validated RawMinerForecast objects."""
        if self._dendrite is None:
            raise RuntimeError("Adapter not connected — call connect() first")

        symbol, timeframe = self.parse_stream_id(request.stream_id)
        now = datetime.now(tz=timezone.utc)
        metagraph = self._metagraph
        block = getattr(metagraph, "block", None) if metagraph else None
        if not axons or not uids:
            return []

        uid_index = (
            {uid: index for index, uid in enumerate(list(metagraph.uids))}
            if metagraph is not None
            else {}
        )
        payload = self._build_query_payload(request)
        semaphore = asyncio.Semaphore(min(16, len(axons)))

        async def _bounded_query(
            task_uid: int, task_axon: Any
        ) -> tuple[int, list[Any] | Any] | None:
            async with semaphore:
                try:
                    return await self._query_single_miner(
                        task_uid,
                        task_axon,
                        payload,
                        timeout,
                    )
                except Exception as exc:
                    logger.debug("Miner %d: query failed: %s", task_uid, exc)
                    return None

        raw_results = await asyncio.gather(
            *[_bounded_query(uid, axon) for uid, axon in zip(uids, axons)],
            return_exceptions=False,
        )

        forecasts: list[RawMinerForecast] = []
        for result in raw_results:
            if result is None:
                continue

            uid, responses = result
            idx = uid_index.get(uid)
            if not responses:
                logger.debug("Miner %d: no response", uid)
                continue

            for response in responses:
                if response is None:
                    continue

                predictions = None
                if isinstance(response, dict):
                    predictions = response.get("predictions")
                    hashed = response.get("hashed_predictions")
                else:
                    predictions = getattr(response, "predictions", None)
                    hashed = getattr(response, "hashed_predictions", None)

                if predictions is None or not self.validate_tensor(
                    predictions, request.prediction_size
                ):
                    logger.debug("Miner %d: invalid or missing response", uid)
                    continue

                incentive = self._safe_index(getattr(metagraph, "I", []), idx)
                vtrust = self._safe_index(
                    getattr(metagraph, "validator_trust", []), idx
                )
                stake = self._safe_index(getattr(metagraph, "S", []), idx)
                if metagraph is not None and idx is not None:
                    hotkey = metagraph.hotkeys[idx]
                else:
                    hotkey = str(uid)

                forecasts.append(
                    RawMinerForecast(
                        window_id=window_id,
                        request_uuid=request_uuid,
                        collected_at=now,
                        miner_uid=uid,
                        miner_hotkey=hotkey,
                        stream_id=request.stream_id,
                        topic_id=request.topic_id,
                        schema_id=request.schema_id,
                        symbol=symbol,
                        timeframe=timeframe,
                        feature_ids=request.feature_ids,
                        prediction_size=request.prediction_size,
                        predictions=predictions,
                        hashed_predictions=hashed,
                        hash_verified=False,
                        incentive_score=incentive,
                        vtrust=vtrust,
                        stake_tao=stake,
                        metagraph_block=block,
                    )
                )

        return forecasts

    @staticmethod
    def verify_hash_commitment(hashed: str | None, predictions: list[float]) -> bool:
        """Verify SHA-256 hash of compact JSON-serialized predictions."""
        if hashed is None:
            return False
        raw = json.dumps(predictions, separators=(",", ":"))
        expected = hashlib.sha256(raw.encode()).hexdigest()
        return hashed == expected

    def get_incentive_scores(self, hotkeys: list[str]) -> dict[str, float]:
        """Extract raw incentive scores for the given hotkeys from the cached metagraph.

        Returns 0.0 for hotkeys not found in the metagraph. Returns all 0.0 if
        metagraph is not loaded.
        """
        if self._metagraph is None:
            logger.warning("get_incentive_scores called but metagraph is None")
            return {hk: 0.0 for hk in hotkeys}

        hotkey_to_idx = {hk: i for i, hk in enumerate(self._metagraph.hotkeys)}
        result: dict[str, float] = {}
        for hk in hotkeys:
            idx = hotkey_to_idx.get(hk)
            if idx is not None:
                result[hk] = float(self._metagraph.I[idx])
            else:
                logger.warning(
                    "Hotkey %s not found in metagraph — using incentive 0.0", hk
                )
                result[hk] = 0.0
        return result

    async def close(self) -> None:
        """Clean up resources."""
        self._dendrite = None
        self._subtensor = None
        self._wallet = None
        self._metagraph = None
