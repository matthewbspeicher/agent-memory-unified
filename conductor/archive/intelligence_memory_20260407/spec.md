# Specification: Intelligence (Vector Memory Loop)

Deeply integrate the `pgvector` memory system into the strategy scan cycles, enabling agents to "remember" market contexts and "recall" historical performance before trading.

## Problem Statement
While we have a basic regime detector and memory manager, our strategies do not yet systematically use historical "memories" to filter or weight their decisions. We need a closed-loop system where every trade outcome is stored as a vector and every new signal triggers a similarity search.

## Objectives
- **Market Context Vectorization**: Convert market state (price action, sentiment, volume) into high-dimensional vectors for storage in `pgvector`.
- **Similarity-Based Filtering**: Signal conviction should be adjusted based on the PnL of historical "neighbors" in the vector space.
- **Automated Autopsy Storage**: Every closed trade must generate a "Memory" that includes the market regime and result.

## Key Requirements

### 1. Vectorization Engine
- Use an embedding model (via LLM client) to vectorize market summaries.
- Store in the `memories` table via the Laravel API or direct DB access.

### 2. Strategy Integration
- Update the base `StructuredAgent` or individual strategies to call `RegimeMemoryManager.recall()` during `scan()`.
- Implement a "Recall Confidence" metric.

### 3. Closed-Loop Learning
- Trigger a "Store Memory" event when a trade is closed.
- Include the final PnL and "What went right/wrong" analysis in the vector metadata.

## Success Criteria
- [ ] Every trade in the `trades` table has a corresponding entry in the `memories` table.
- [ ] Similarity searches return relevant historical regimes during live trading.
- [ ] Backtest results show improved Sharpe ratio when Memory Loop is enabled.
