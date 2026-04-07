# Implementation Plan: Intelligence (Vector Memory Loop)

## Phase 1: Embedding & Storage
- [x] Task: Implement `MarketVectorService`
    - [x] Logic to generate market context strings for embedding in `trading/memory/vector_service.py`.
    - [x] Integration with LLM embedding endpoint in `trading/llm/client.py`.
- [x] Task: DB-Backed Vector Storage
    - [x] Verified `pgvector` usage via `Remembr` API.
    - [x] Integrated `RegimeMemoryManager.store_regime` into `TradeReflector.reflect`.

## Phase 2: Similarity Search & Recall
- [x] Task: Implement `SimilarityFilter`
    - [x] Logic to query `pgvector` for similar historical states in `trading/intelligence/similarity.py`.
    - [x] Statistical aggregation of past outcomes (Win Rate of neighbors).
- [x] Task: Agent Integration
    - [x] Wired the filter into `RegimeProvider` which enriches `BittensorAlphaAgent` signals.

## Phase 3: Validation & Backtesting
- [x] Task: backtest-mcp Validation
    - [x] Run a backtest with Memory Loop enabled (Consensus pipeline verified).
    - [x] Verified full pipeline: Taoshi Replay -> Aggregator (Weighted) -> Intel enrichment -> Execution.
    - [x] Results: 501 trades, Win Rate 44.97% (Initial baseline for memory optimization).
