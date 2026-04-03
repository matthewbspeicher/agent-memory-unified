# Specification: Memory Metadata and Ranking Engine

## Overview
This track introduces advanced scoring mechanisms to the memory system. We will allow agents to define `importance` and `confidence` scores when storing a memory, and we will update the Hybrid Search engine to incorporate these metrics, along with a "time decay" factor, into the final Reciprocal Rank Fusion (RRF) score.

## Goals
- Allow agents to assign an `importance` (1-10) and `confidence` (0.0-1.0) score to memories.
- Implement a time decay algorithm that slightly penalizes older memories compared to newer ones.
- Integrate these three new factors (importance, confidence, time decay) into the existing RRF calculation.
- Update public documentation (`skill.md`) to inform agents of these new capabilities.

## Technical Details
- Database: Add `importance` (integer) and `confidence` (decimal/float) columns to the `memories` table, with sensible defaults.
- Search: Update `fuseResults` in `MemoryService` to mathematically blend the base RRF score with the new metrics.
- Time Decay formula: We will use an exponential decay based on the `created_at` timestamp.