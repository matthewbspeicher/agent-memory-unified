"""Multi-subnet integration for Bittensor.

Enables querying other subnets for complementary signals:
- SN28: S&P 500 Oracle (equity index predictions)
- SN15: BitQuant (AI-driven crypto analysis)

Reference: https://docs.bittensor.com/
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class SubnetSignal:
    """Signal from a Bittensor subnet."""

    subnet: int  # subnet UID
    hotkey: str  # miner hotkey
    signal_type: str  # e.g., "sp500", "crypto", "sentiment"
    value: float  # signal value
    confidence: float  # 0-1 confidence
    timestamp: float  # unix timestamp


class SubnetQuerier:
    """Query multiple Bittensor subnets for signals.

    Currently supports:
    - Subnet 28 (S&P 500 Oracle)
    - Subnet 15 (BitQuant)
    """

    def __init__(
        self,
        wallet: Any,
        network: str = "finney",
    ):
        import bittensor as bt

        self.wallet = wallet
        self.network = network
        self._subtensor = bt.Subtensor(network=network)
        self._dendrite = bt.Dendrite(wallet=wallet)

    async def query_subnet(
        self,
        subnet_uid: int,
        timeout: float = 12.0,
    ) -> list[SubnetSignal]:
        """Query a specific subnet for signals.

        Args:
            subnet_uid: The subnet UID to query
            timeout: Query timeout in seconds

        Returns:
            List of SubnetSignal objects
        """
        try:
            import bittensor as bt

            # Get metagraph for this subnet (Bittensor v10 API)
            metagraph = self._subtensor.metagraph(netuid=subnet_uid)

            # Get axons for active miners (stake > 0)
            # metagraph.S is stake vector indexed by uid order
            axons = [
                axon
                for uid, axon in zip(metagraph.uids, metagraph.axons)
                if metagraph.S[uid] > 0
            ]

            if not axons:
                logger.warning("No active miners on subnet %d", subnet_uid)
                return []

            # Query a subset of miners
            responses = await self._dendrite(
                axons=axons[:10],  # Query top 10 by stake
                synapse=bt.Synapse(),
                timeout=timeout,
            )

            signals = []
            items = (
                list(responses) if isinstance(responses, (list, tuple)) else [responses]
            )
            for resp in items:
                if not resp or not hasattr(resp, "neuron"):
                    continue

                neuron = getattr(resp, "neuron")
                if neuron is None or not hasattr(neuron, "hotkey"):
                    continue

                signal = SubnetSignal(
                    subnet=subnet_uid,
                    hotkey=getattr(neuron, "hotkey", ""),
                    signal_type=self._get_signal_type(subnet_uid),
                    value=0.0,  # Would parse from response
                    confidence=0.5,
                    timestamp=getattr(neuron, "last_update", 0.0),
                )
                signals.append(signal)

            logger.info("Queried subnet %d, got %d responses", subnet_uid, len(signals))
            return signals

        except Exception as e:
            logger.error("Failed to query subnet %d: %s", subnet_uid, e)
            return []

    def _get_signal_type(self, subnet_uid: int) -> str:
        """Map subnet UID to signal type."""
        mapping = {
            28: "sp500",
            15: "crypto_analysis",
            8: "ptn",  # Our subnet
        }
        return mapping.get(subnet_uid, "unknown")

    async def query_sp500_oracle(self) -> list[SubnetSignal]:
        """Query SN28 for S&P 500 predictions."""
        return await self.query_subnet(28)

    async def query_bitquant(self) -> list[SubnetSignal]:
        """Query SN15 for BitQuant analysis."""
        return await self.query_subnet(15)

    async def query_all(self) -> dict[str, list[SubnetSignal]]:
        """Query all integrated subnets."""
        results = {}

        for subnet_name, subnet_uid in [("sp500", 28), ("bitquant", 15)]:
            try:
                results[subnet_name] = await self.query_subnet(subnet_uid)
            except Exception as e:
                logger.warning(
                    "Failed to query %s (SN%d): %s", subnet_name, subnet_uid, e
                )
                results[subnet_name] = []

        return results


def create_querier() -> SubnetQuerier | None:
    """Create a SubnetQuerier if wallet is available."""
    try:
        import bittensor as bt

        wallet = bt.Wallet()
        if not wallet.hotkey:
            logger.warning("No hotkey configured, multi-subnet disabled")
            return None
        return SubnetQuerier(wallet=wallet)
    except Exception as e:
        logger.warning("Failed to create subnet querier: %s", e)
        return None
