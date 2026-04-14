"""Tests for per-symbol miner rankings."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from integrations.bittensor.models import (
    MinerRanking,
    MinerRankingInput,
    RankingConfig,
    RankingWeights,
    MinerAccuracyRecord
)
from integrations.bittensor.ranking import compute_rankings, DIRECTION_HEAVY
from integrations.bittensor.evaluator import MinerEvaluator

@pytest.mark.asyncio
async def test_per_symbol_ranking_logic():
    """Verify that rankings can be computed and stored per symbol."""
    store = AsyncMock()
    data_bus = MagicMock()
    evaluator = MinerEvaluator(store, data_bus)
    
    # Mock data
    hotkeys = ["hk1", "hk2"]
    symbols = ["BTCUSD", "ETHUSD"]
    
    store.get_distinct_miner_hotkeys.return_value = hotkeys
    store.get_distinct_symbols.return_value = symbols
    store.get_latest_incentive_scores.return_value = {"hk1": 0.5, "hk2": 0.3}
    
    # Mock rollups for BTCUSD
    store.get_accuracy_rollup.side_effect = [
        # BTCUSD rollup
        {
            "hk1": {"windows_evaluated": 20, "direction_accuracy": 0.8, "mean_magnitude_error": 0.01, "mean_path_correlation": 0.9},
            "hk2": {"windows_evaluated": 20, "direction_accuracy": 0.6, "mean_magnitude_error": 0.02, "mean_path_correlation": 0.7}
        },
        # ETHUSD rollup
        {
            "hk1": {"windows_evaluated": 20, "direction_accuracy": 0.5, "mean_magnitude_error": 0.05, "mean_path_correlation": 0.4},
            "hk2": {"windows_evaluated": 20, "direction_accuracy": 0.9, "mean_magnitude_error": 0.005, "mean_path_correlation": 0.95}
        },
        # Aggregate rollup
        {
            "hk1": {"windows_evaluated": 40, "direction_accuracy": 0.7, "mean_magnitude_error": 0.02, "mean_path_correlation": 0.75},
            "hk2": {"windows_evaluated": 40, "direction_accuracy": 0.7, "mean_magnitude_error": 0.015, "mean_path_correlation": 0.8}
        }
    ]
    
    store.get_miner_max_drawdowns.return_value = {"hk1": 0.02, "hk2": 0.03}
    
    await evaluator.refresh_rankings()
    
    # Verify update_miner_ranking was called for each hotkey x (symbols + aggregate)
    # Total calls: 2 hotkeys * 3 (BTC, ETH, Aggregate) = 6
    assert store.update_miner_ranking.call_count == 6
    
    # Check one specific call
    calls = store.update_miner_ranking.call_args_list
    rankings = [c.args[0] for c in calls]
    
    btc_rankings = [r for r in rankings if r.symbol == "BTCUSD"]
    eth_rankings = [r for r in rankings if r.symbol == "ETHUSD"]
    agg_rankings = [r for r in rankings if r.symbol == "aggregate"]
    
    assert len(btc_rankings) == 2
    assert len(eth_rankings) == 2
    assert len(agg_rankings) == 2
    
    # In BTC, hk1 is better
    hk1_btc = next(r for r in btc_rankings if r.miner_hotkey == "hk1")
    hk2_btc = next(r for r in btc_rankings if r.miner_hotkey == "hk2")
    assert hk1_btc.hybrid_score > hk2_btc.hybrid_score
    
    # In ETH, hk2 is better
    hk1_eth = next(r for r in eth_rankings if r.miner_hotkey == "hk1")
    hk2_eth = next(r for r in eth_rankings if r.miner_hotkey == "hk2")
    assert hk2_eth.hybrid_score > hk1_eth.hybrid_score
