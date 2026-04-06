from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import math
from datetime import datetime, timezone

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
                self._subtensor = bt.subtensor(
                    network=self._network,
                    chain_endpoint=self._endpoint,
                )
                self._wallet = bt.wallet(
                    name=self._wallet_name,
                    path=self._hotkey_path,
                    hotkey=self._hotkey,
                )
                self._dendrite = bt.dendrite(wallet=self._wallet)
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

    def build_request(self) -> PredictionRequest:
        """Build a prediction request using protocol defaults."""
        return PredictionRequest()

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

        forecasts: list[RawMinerForecast] = []
        for uid, axon in zip(uids, axons):
            try:
                response = await self._dendrite(
                    axons=[axon],
                    timeout=timeout,
                )
                predictions = (
                    getattr(response, "predictions", None) if response else None
                )
                hashed = (
                    getattr(response, "hashed_predictions", None) if response else None
                )

                if predictions is None or not self.validate_tensor(
                    predictions, request.prediction_size
                ):
                    logger.debug("Miner %d: invalid or missing response", uid)
                    continue

                idx = list(metagraph.uids).index(uid) if metagraph else None
                incentive = metagraph.I[idx] if metagraph and idx is not None else None
                vtrust = (
                    getattr(metagraph, "validator_trust", [None] * ((idx or 0) + 1))[
                        idx
                    ]
                    if metagraph and idx is not None
                    else None
                )
                stake = (
                    getattr(metagraph, "S", [None] * ((idx or 0) + 1))[idx]
                    if metagraph and idx is not None
                    else None
                )
                hotkey = (
                    metagraph.hotkeys[idx]
                    if metagraph and idx is not None
                    else str(uid)
                )

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
            except Exception as e:
                logger.debug("Miner %d: query failed: %s", uid, e)
                continue

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
