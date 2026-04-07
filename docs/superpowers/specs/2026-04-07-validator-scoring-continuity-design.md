# Specification: Validator Scoring Continuity & Pipeline Persistence

## Overview
The "Scoring Continuity" track ensures that the Bittensor Validator node maintains its state across restarts and correctly integrates signals from the official Taoshi PTN bridge into our internal scoring and evaluation pipeline.

## Goals
1.  **Eliminate Signal Duplication:** Prevent `TaoshiBridge` from re-emitting signals for positions it has already processed.
2.  **Unify Data Ingestion:** Ensure all signals (from the bridge and direct queries) are stored in `BittensorStore` for historical analysis.
3.  **Ensure Scoring Resilience:** Allow the `BittensorEvaluator` to resume scoring and ranking miners without data loss after a system restart.

## Functional Requirements

### 1. Persistent Position Tracking
*   **Database Table:** Create `bittensor_processed_positions` (UUID, hotkey, processed_at).
*   **Bridge Logic:**
    *   On startup, `TaoshiBridge` loads existing UUIDs from the database into its `_seen_position_uuids` set.
    *   After processing a new position file, the bridge inserts the UUID into the database.

### 2. Bridge-to-Store Integration
*   `TaoshiBridge` will now call `BittensorStore.save_raw_forecasts()` for every new position detected.
*   **Data Mapping:**
    *   `window_id`: Derived from the position's `open_ms` timestamp (aligned to the nearest 30-minute bucket).
    *   `predictions`: Derived from the Taoshi position's order price.
    *   `hash_verified`: Set to `True` (since Taoshi positions are inherently verified by the protocol).

### 3. Evaluator Continuity
*   The `BittensorEvaluator` will use the unified `bittensor_raw_forecasts` table as its source of truth.
*   It will automatically pick up bridge-ingested forecasts during its periodic "mature window" scans.

## Non-Functional Requirements
*   **Idempotency:** Re-running the bridge or evaluator on the same data should not create duplicate records.
*   **Performance:** The database lookups for UUIDs should be indexed to ensure sub-millisecond overhead during bridge polls.

## Acceptance Criteria
- [ ] `TaoshiBridge` does not emit duplicate `AgentSignal` objects after a restart.
- [ ] Signals from the Taoshi `validation/miners` files appear in the `bittensor_raw_forecasts` database table.
- [ ] `BittensorEvaluator` successfully scores a window that was populated by the bridge.
- [ ] Miner rankings are persisted and reload correctly on startup.

## Out of Scope
*   Fixing the "0% response rate" for the legacy direct dendrite queries.
*   Modifying the official Taoshi validator code in `taoshi-ptn/`.
