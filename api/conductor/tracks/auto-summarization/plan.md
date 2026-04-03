# Track 2: Auto-Summarization & Compaction 🧠

Implementation plan for efficient agent memory management.

## Phase 1: Background Summarization
- [ ] Create `SummarizeMemory` job.
- [ ] Update `MemoryService` to dispatch summarization for long memories asynchronously.
- [ ] Add `summary` field to `Memory` resource transformation.

## Phase 2: Compaction API Enhancements
- [ ] Refactor `MemoryController::compact` to support more advanced synthesis.
- [ ] Implement `SynthesisService` for merging multiple memories into high-density nodes.
- [ ] Add `relations` tracking for compacted memories (provenance).

## Phase 3: Auto-Compaction Policies
- [ ] Implement `AutoCompactMemories` command/job.
- [ ] Add `compaction_threshold` to `Agent` configuration.
- [ ] Periodically compact older, lower-importance memories into summaries.
