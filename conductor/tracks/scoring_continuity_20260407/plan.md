# Implementation Plan: Validator Scoring Continuity & Pipeline Persistence

## Phase 1: Persistence Layer
- [x] Task: Create `bittensor_processed_positions` table
    - [x] Write failing test for table existence and schema in `trading/tests/storage/test_db.py`
    - [x] Add table definition to initialization logic or create migration script
    - [x] Verify test passes
- [x] Task: Implement DB-backed UUID tracking in `TaoshiBridge`
    - [x] Write failing test in `trading/tests/integration/test_taoshi_bridge_persistence.py`
    - [x] Update `TaoshiBridge` to load/save UUIDs using the database
    - [x] Verify test passes
- [x] Task: Conductor - User Manual Verification 'Persistence Layer' (Protocol in workflow.md)

## Phase 2: Ingestion & Evaluation
- [x] Task: Integrate `TaoshiBridge` with `BittensorStore`
    - [x] Write failing test for bridge signal ingestion
    - [x] Implement `RawMinerForecast` transformation and store injection in `TaoshiBridge`
    - [x] Verify test passes
- [x] Task: Verify `BittensorEvaluator` continuity
    - [x] OBSOLETE: `BittensorEvaluator` was removed in commit 0cccffdbc9d37f5262121d6306b6586e8e43aec8. The official Taoshi validator handles scoring.
- [x] Task: Conductor - User Manual Verification 'Ingestion & Evaluation' (Protocol in workflow.md)
