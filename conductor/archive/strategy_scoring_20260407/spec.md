# Specification: Strategy & Scoring (Miner Accuracy & Ensemble Wiring)

Implement accuracy-based ranking for Bittensor miners and activate multi-factor ensemble strategies.

## Problem Statement
Currently, all miner signals are weighted equally in the consensus. We need to reward high-performing miners and reduce the impact of inaccurate ones. Additionally, several advanced strategies are implemented but not yet "wired" into the main execution pipeline.

## Objectives
- **Miner Accuracy Scoring**: Track predicted vs. actual price movement for every miner signal.
- **Weighted Consensus**: Update `MinerConsensusAggregator` to use accuracy scores as weights.
- **Ensemble Activation**: Integrate existing multi-factor strategies (e.g., Sentiment + Technical) into the `OpportunityRouter`.

## Key Requirements

### 1. Accuracy Engine
- Track "Forecast" vs "Realized" price for each miner signal.
- Store results in the `bittensor_accuracy_records` table.
- Calculate a rolling accuracy score (0.0 to 1.0) per miner.

### 2. Weighted Consensus
- `MinerConsensusAggregator` should query `bittensor_miner_rankings`.
- Weighted signal = sum(Signal_i * Weight_i) / sum(Weight_i).

### 3. Ensemble Wiring
- Audit `trading/strategies/` for idle multi-factor strategies.
- Add them to the `agents_config` in `trading/config.py`.

## Success Criteria
- [ ] Accuracy records are successfully generated after price window realization.
- [ ] Miner weights are reflected in the `bittensor_consensus` signals.
- [ ] Ensemble strategies are producing opportunities in the dashboard.
