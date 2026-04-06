from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from integrations.bittensor.weight_setter import WeightSetter
from integrations.bittensor.models import MinerRanking


def _make_ranking(hotkey: str, hybrid_score: float) -> MinerRanking:
    return MinerRanking(
        miner_hotkey=hotkey,
        windows_evaluated=100,
        direction_accuracy=0.6,
        mean_magnitude_error=0.01,
        mean_path_correlation=0.5,
        internal_score=0.7,
        latest_incentive_score=0.1,
        hybrid_score=hybrid_score,
        alpha_used=0.5,
        updated_at=datetime.now(tz=timezone.utc),
    )


class TestWeightSetter:
    def test_normalize_scores_to_weights(self):
        """Hybrid scores should normalize to weights summing to 1.0."""
        setter = WeightSetter(
            adapter=MagicMock(),
            store=MagicMock(),
            netuid=8,
            interval_blocks=100,
        )
        rankings = [
            _make_ranking("hk_a", 0.8),
            _make_ranking("hk_b", 0.6),
            _make_ranking("hk_c", 0.2),
        ]
        hotkey_to_uid = {"hk_a": 0, "hk_b": 1, "hk_c": 2}

        uids, weights = setter.compute_weight_vector(rankings, hotkey_to_uid)

        assert len(uids) == 3
        assert len(weights) == 3
        assert abs(sum(weights) - 1.0) < 1e-6
        # Highest hybrid_score should get highest weight
        assert weights[uids.index(0)] > weights[uids.index(1)]
        assert weights[uids.index(1)] > weights[uids.index(2)]

    def test_empty_rankings_returns_empty(self):
        setter = WeightSetter(
            adapter=MagicMock(),
            store=MagicMock(),
            netuid=8,
            interval_blocks=100,
        )
        uids, weights = setter.compute_weight_vector([], {})
        assert uids == []
        assert weights == []

    def test_single_miner_gets_full_weight(self):
        setter = WeightSetter(
            adapter=MagicMock(),
            store=MagicMock(),
            netuid=8,
            interval_blocks=100,
        )
        rankings = [_make_ranking("hk_a", 0.9)]
        uids, weights = setter.compute_weight_vector(rankings, {"hk_a": 0})
        assert uids == [0]
        assert abs(weights[0] - 1.0) < 1e-6

    def test_miners_not_in_metagraph_excluded(self):
        setter = WeightSetter(
            adapter=MagicMock(),
            store=MagicMock(),
            netuid=8,
            interval_blocks=100,
        )
        rankings = [
            _make_ranking("hk_a", 0.8),
            _make_ranking("hk_missing", 0.6),
        ]
        hotkey_to_uid = {"hk_a": 0}  # hk_missing not in metagraph

        uids, weights = setter.compute_weight_vector(rankings, hotkey_to_uid)
        assert uids == [0]
        assert abs(weights[0] - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_set_weights_calls_subtensor(self):
        mock_adapter = MagicMock()
        mock_subtensor = MagicMock()
        mock_wallet = MagicMock()
        mock_adapter._subtensor = mock_subtensor
        mock_adapter._wallet = mock_wallet

        mock_metagraph = MagicMock()
        mock_metagraph.hotkeys = ["hk_a", "hk_b"]
        mock_metagraph.uids = [0, 1]
        mock_adapter._metagraph = mock_metagraph
        mock_adapter.metagraph = mock_metagraph
        mock_adapter.refresh_metagraph = AsyncMock()

        mock_store = AsyncMock()
        mock_store.get_miner_rankings = AsyncMock(
            return_value=[
                _make_ranking("hk_a", 0.8),
                _make_ranking("hk_b", 0.4),
            ]
        )

        mock_subtensor.set_weights = MagicMock(return_value=(True, "ok"))

        setter = WeightSetter(
            adapter=mock_adapter,
            store=mock_store,
            netuid=8,
            interval_blocks=100,
            min_rankings=1,
        )

        success = await setter.set_weights_once()

        assert success is True
        mock_subtensor.set_weights.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_weights_skips_when_too_few_rankings(self):
        mock_adapter = MagicMock()
        mock_adapter.metagraph = MagicMock()
        mock_adapter.metagraph.hotkeys = ["hk_a"]
        mock_adapter.metagraph.uids = [0]

        mock_store = AsyncMock()
        mock_store.get_miner_rankings = AsyncMock(
            return_value=[
                _make_ranking("hk_a", 0.8),
            ]
        )

        setter = WeightSetter(
            adapter=mock_adapter,
            store=mock_store,
            netuid=8,
            interval_blocks=100,
            min_rankings=5,  # requires 5, only have 1
        )

        success = await setter.set_weights_once()
        assert success is False
