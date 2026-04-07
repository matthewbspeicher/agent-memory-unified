import pytest
from integrations.bittensor.evaluator import MinerEvaluator
from integrations.bittensor.models import MinerRankingInput

def test_miner_elimination_drawdown():
    # Setup evaluator with mock store/data_bus
    from unittest.mock import MagicMock
    evaluator = MinerEvaluator(MagicMock(), MagicMock())
    
    # 15% drawdown (Vanta threshold is typically 10%)
    input_data = MinerRankingInput(
        miner_hotkey="miner_1",
        windows_evaluated=10,
        direction_accuracy=0.4,
        mean_magnitude_error=0.1,
        mean_path_correlation=0.0,
        raw_incentive_score=0.5,
        max_drawdown=0.15 
    )
    
    status = evaluator._determine_lifecycle_status(input_data)
    assert status == "eliminated"
    
def test_miner_probation():
    from unittest.mock import MagicMock
    evaluator = MinerEvaluator(MagicMock(), MagicMock())
    
    # High error, but hasn't hit DD limit
    input_data = MinerRankingInput(
        miner_hotkey="miner_2",
        windows_evaluated=20,
        direction_accuracy=0.2,
        mean_magnitude_error=0.5,
        mean_path_correlation=-0.2,
        raw_incentive_score=0.1,
        max_drawdown=0.05 
    )
    
    status = evaluator._determine_lifecycle_status(input_data)
    assert status == "probation"
