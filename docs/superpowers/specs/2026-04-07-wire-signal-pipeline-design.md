# Specification: Wire Signal Pipeline End-to-End (TP-002)

## Overview
The goal is to wire the complete signal pipeline so miner positions from `TaoshiBridge` actually reach trading strategies and generate trade decisions. This bridges the gap between individual miner signals (`bittensor_miner_position`) and the consensus signals (`bittensor_consensus`) expected by the trading agents.

## Architecture & Responsibility
*   **Component:** `MinerConsensusAggregator` in `trading/integrations/bittensor/consensus_aggregator.py`.
*   **Role:** Subscribes to raw `bittensor_miner_position` signals from the `SignalBus` and publishes aggregated `bittensor_consensus` signals.

## Data Flow & Aggregation Logic
*   **Sliding Window:** Maintains a short-term memory (e.g., 5-minute rolling window) of the latest position for each miner, grouped by symbol (e.g., BTCUSD).
*   **Consensus Rules:**
    *   **Direction:** The majority direction (bullish, bearish, or flat).
    *   **Confidence:** The ratio of miners agreeing on that direction (e.g., 80% bullish).
    *   **Expected Return:** An average of the leverage or expected return from the agreeing miners.
*   **Emission:** Emits a `bittensor_consensus` signal back onto the bus when a new consensus is formed or updated.

## Consumers & Wiring
*   **The Agent:** The existing `BittensorAlphaAgent` (in `trading/strategies/bittensor_consensus.py`) listens for `bittensor_consensus` signals and converts them into trade opportunities.
*   **App Lifespan:** The `MinerConsensusAggregator` will be instantiated in the FastAPI startup lifecycle (`trading/api/app.py`), sharing the `SignalBus` instance with the bridge and the agents.
*   **Monitoring:** The current real-time consensus state will be exposed on the `/api/bittensor/status` endpoint for the React dashboard.

## Error Handling & Edge Cases
*   **Stale Data:** Positions older than the sliding window must be expired/removed from the consensus calculation.
*   **Conflicting Signals:** If no clear majority exists (e.g., 50/50 split), the confidence will be low, and the downstream agent will likely ignore it based on its own thresholds.
*   **Single Miner:** Handled gracefully; consensus is 100% for that single miner's direction, but total miner count is passed along for the agent to weigh.

## Testing Strategy
*   **Unit Tests:** Create `trading/tests/unit/test_consensus_aggregator.py` to test windowing, expiry, and consensus calculation logic with mocked signals.
*   **Integration Tests:** Update `trading/tests/integration/test_bittensor_e2e.py` to verify the full pipeline: Bridge -> SignalBus -> Aggregator -> SignalBus -> BittensorAlphaAgent.
