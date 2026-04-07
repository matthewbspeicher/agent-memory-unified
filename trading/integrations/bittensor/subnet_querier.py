"""Multi-subnet integration for Bittensor.

Enables querying other subnets for complementary signals:
- SN28: S&P 500 Oracle (equity index predictions)
- SN15: BitQuant (AI-driven crypto analysis)

Reference: https://docs.bittensor.com/
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import bittensor as bt

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
        wallet: bt.wallet.Wallet,
        network: str = "finney",
    ):
        self.wallet = wallet
        self.network = network
        self._subtensor = bt.subtensor(network=network)
        self._dendrite = bt.dendrite(wallet=wallet)

    def query_subnet(
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
            # Get metagraph for this subnet
            metagraph = self._subtensor.metagraph(subnet_uid)

            # Get axons for active miners
            axons = [
                axon
                for axon in metagraph.axons
                if metagraph.neurons[axon.uid].stake > 0
            ]

            if not axons:
                logger.warning("No active miners on subnet %d", subnet_uid)
                return []

            # Query a subset of miners
            responses = self._dendrite(
                axons=axons[:10],  # Query top 10 by stake
                synapse=bt.Synapse(),
                timeout=timeout,
            )

            signals = []
            for resp in responses:
                if resp.neuron and hasattr(resp, "hotkey"):
                    signal = SubnetSignal(
                        subnet=subnet_uid,
                        hotkey=resp.neuron.hotkey,
                        signal_type=self._get_signal_type(subnet_uid),
                        value=0.0,  # Would parse from response
                        confidence=0.5,
                        timestamp=resp.neuron.last_update,
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

    def query_sp500_oracle(self) -> list[SubnetSignal]:
        """Query SN28 for S&P 500 predictions."""
        return self.query_subnet(28)

    def query_bitquant(self) -> list[SubnetSignal]:
        """Query SN15 for BitQuant analysis."""
        return self.query_subnet(15)

    def query_all(self) -> dict[str, list[SubnetSignal]]:
        """Query all integrated subnets."""
        results = {}

        for subnet_name, subnet_uid in [("sp500", 28), ("bitquant", 15)]:
            try:
                results[subnet_name] = self.query_subnet(subnet_uid)
            except Exception as e:
                logger.warning(
                    "Failed to query %s (SN%d): %s", subnet_name, subnet_uid, e
                )
                results[subnet_name] = []

        return results


def create_querier() -> SubnetQuerier | None:
    """Create a SubnetQuerier if wallet is available."""
    try:
        wallet = bt.wallet()
        if not wallet.hotkey:
            logger.warning("No hotkey configured, multi-subnet disabled")
            return None
        return SubnetQuerier(wallet=wallet)
    except Exception as e:
        logger.warning("Failed to create subnet querier: %s", e)
        return None
