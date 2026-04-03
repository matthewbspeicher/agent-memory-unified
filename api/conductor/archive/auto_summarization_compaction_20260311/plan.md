# Implementation Plan: Auto-Summarization & Compaction

## Phase 1: Summarization Service [checkpoint: 80128c9]
- [x] Task: Create SummarizationService [commit: aa4d8b4]
    - [ ] Create a service class to interact with the Gemini `generateContent` API for summarization.
    - [ ] Write a test verifying the service correctly parses the Gemini response.
- [x] Task: Update Database for Archiving [commit: aa4d8b4]
    - [ ] Create a migration to add `archived` to the `visibility` enum.
- [x] Task: Conductor - User Manual Verification 'Phase 1: Summarization Service' (Protocol in workflow.md) [commit: 80128c9]

## Phase 2: Compaction API [checkpoint: cb66c9c]
- [x] Task: Implement Compaction Endpoint [commit: 758b758]
    - [ ] Create `POST /api/v1/memories/compact` in `MemoryController`.
    - [ ] Accept a list of memory IDs or a search query to compact.
    - [ ] Use `SummarizationService` to generate the summary, create the new memory, and archive the old ones.
- [x] Task: Write Tests for Compaction [commit: 758b758]
    - [ ] Write a feature test verifying memories are compacted, a new one is created, and old ones are archived.
- [x] Task: Conductor - User Manual Verification 'Phase 2: Compaction API' (Protocol in workflow.md) [commit: cb66c9c]

## Phase 3: Documentation [checkpoint: 793d822]
- [x] Task: Update `skill.md` [commit: ae7ddb9]
    - [ ] Document the new compaction endpoint and its benefits for context windows.
- [x] Task: Conductor - User Manual Verification 'Phase 3: Documentation' (Protocol in workflow.md) [commit: 793d822]