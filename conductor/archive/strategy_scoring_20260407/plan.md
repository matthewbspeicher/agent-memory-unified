# Implementation Plan: Strategy & Scoring

## Phase 1: Miner Accuracy Engine
- [x] Task: Implement `MinerEvaluator`
    - [x] Logic to check price after signal expiry in `trading/integrations/bittensor/evaluator.py`.
    - [x] Record results in `bittensor_accuracy_records` via `BittensorStore`.
- [x] Task: Background Evaluator Job
    - [x] Create a periodic task to realize "pending" signals in `api/app.py`.

## Phase 2: Weighted Consensus
- [x] Task: Update `MinerConsensusAggregator`
    - [x] Fetch rankings from DB.
    - [x] Apply weights to the aggregation logic in `consensus_aggregator.py`.

## Phase 3: Ensemble Strategy Wiring
- [x] Task: Audit & Register Strategies
    - [x] Verified `MultiFactorAgent` in `trading/strategies/multi_factor.py`.
    - [x] Added `bittensor_alpha_ensemble` and `crypto_multi_factor` to `trading/agents.yaml`.
    - [x] Integrated "Gate 9" (Intel Layer) into `BittensorAlphaAgent`.
