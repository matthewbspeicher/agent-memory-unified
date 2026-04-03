# Implementation Plan: Enhance semantic search quality for the Commons

## Phase 1: Evaluation and Metric Setup [checkpoint: f042a45]
- [x] Task: Set up test framework for search accuracy [commit: a1efaf0]
    - [ ] Write tests for baseline search accuracy.
    - [ ] Implement evaluation scripts to score search results.
- [x] Task: Analyze current pgvector performance [commit: d0d8659]
    - [ ] Add performance telemetry for vector search queries.
    - [ ] Document baseline performance metrics.
- [x] Task: Conductor - User Manual Verification 'Phase 1: Evaluation and Metric Setup' (Protocol in workflow.md) [commit: f042a45]

## Phase 2: Hybrid Search Implementation [checkpoint: fc0a320]
- [x] Task: Implement keyword search index [commit: 9ad1ef7]
    - [ ] Add full-text search indexes on memory text.
    - [ ] Write tests for keyword search endpoints.
- [x] Task: Combine vector and keyword search [commit: 60b6134]
    - [ ] Update MemoryService to use hybrid search (RRF or similar).
    - [ ] Write tests verifying hybrid search results.
- [x] Task: Conductor - User Manual Verification 'Phase 2: Hybrid Search Implementation' (Protocol in workflow.md) [commit: fc0a320]

## Phase 3: Deployment and Tuning [checkpoint: 8915756]
- [x] Task: Optimize embedding models [commit: e2cdfd9]
    - [ ] Evaluate alternative OpenAI embedding models if necessary.
    - [ ] Write tests to verify new embeddings don't break existing data.
- [x] Task: Update the Commons Feed [commit: 60b6134]
    - [ ] Implement enhanced search in the Commons API endpoint.
    - [ ] Write tests for Commons Feed retrieval.
- [x] Task: Conductor - User Manual Verification 'Phase 3: Deployment and Tuning' (Protocol in workflow.md) [commit: 8915756]