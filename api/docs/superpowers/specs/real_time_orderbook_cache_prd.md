# Real-Time Orderbook Cache PRD

## HR Eng

| Real-Time Orderbook Cache PRD |  | Transforming high-latency HTTP pre-flight checks into sub-millisecond deterministic matching using WebSocket-driven in-memory L2 cache. |
| :---- | :---- | :---- |
| **Author**: Pickle Rick **Contributors**: Gemini CLI **Intended audience**: Engineering, Quantitative Trading | **Status**: Draft **Created**: 2026-04-01 | **Self Link**: [Link] **Context**: optimization_paths_analysis.md | 

## Introduction

The current arbitrage system relies on sequential HTTP polling to validate market depth before executing orders. This introduces a critical latency bottleneck (50ms - 300ms) that results in execution slippage and reduced profitability. By maintaining a real-time, in-memory L2 orderbook cache fueled by the Polymarket WebSocket feed, we can perform pre-flight checks in $O(1)$ time.

## Problem Statement

**Current Process:** The system polls market orderbooks via REST API during the `_check_preflight_slippage` phase of the arbitrage loop.
**Primary Users:** ArbCoordinator, Quantitative Trading Agents.
**Pain Points:** 
- REST polling is synchronous and high-latency.
- Market depth changes between the poll and the execution (slippage).
- Rate-limiting on REST endpoints restricts high-frequency validation.
**Importance:** In arbitrage, every millisecond counts. Moving to a real-time cache is the difference between a profitable fill and a stale-price loss.

## Objective & Scope

**Objective:** Reduce pre-flight validation latency to <1ms and ensure execution against the most recent market state.
**Ideal Outcome:** Arbitrage legs are matched against a local mirror of the orderbook that updates in real-time.

### In-scope or Goals
- Implementation of a `WebSocketClient` for Polymarket L2 data.
- Development of a thread-safe `OrderbookCache` (L2 depth).
- Integration of the cache into the pre-flight slippage logic.
- Graceful reconnection and re-synchronization logic.

### Not-in-scope or Non-Goals
- Historical data storage.
- Order execution management (handled by existing services).
- Multi-exchange support (Polymarket focus for Phase 1).

## Product Requirements

### Critical User Journeys (CUJs)
1. **Low-Latency Validation**: The `ArbCoordinator` requests a slippage check; the system returns an immediate `Boolean` based on local memory rather than a network trip.
2. **Real-Time Sync**: A price update occurs on Polymarket; the local cache reflects this change within <5ms of packet arrival.

### Functional Requirements

| Priority | Requirement | User Story |
| :---- | :---- | :---- |
| P0 | WebSocket L2 Stream | As a trader, I want to receive real-time updates so I always have the latest price. |
| P1 | In-Memory Depth Cache | As an execution engine, I want to query orderbook depth in $O(1)$ time. |
| P1 | Reconnection Logic | As a system, I want to automatically reconnect if the stream drops. |
| P2 | Cache Staleness Monitor | As a risk manager, I want to invalidate the cache if updates haven't been received for >500ms. |

## Assumptions

- Polymarket's WebSocket API remains stable.
- The local network latency to the exchange is minimized.

## Risks & Mitigations

- **Risk**: WebSocket connection drops -> **Mitigation**: Implement heartbeat monitoring and automatic re-sync via REST snapshot on reconnect.
- **Risk**: Race conditions in cache updates -> **Mitigation**: Use atomic operations or appropriate locking mechanisms for the L2 map.

## Tradeoff

- **Option**: Polling more frequently. **Pros**: Simpler code. **Cons**: High latency, rate-limiting.
- **Option**: Real-Time Cache. **Pros**: Zero-latency queries, higher accuracy. **Cons**: Increased memory usage, complex sync logic.
- **Chosen**: Real-Time Cache for maximum competitive advantage.

## Business Benefits/Impact/Metrics

**Success Metrics:**

| Metric | Current State (Benchmark) | Future State (Target) | Savings/Impacts |
| :---- | :---- | :---- | :---- |
| *Pre-flight Latency* | ~150ms | <1ms | 99% reduction |
| *Execution Slippage* | ~5-10 bps | <2 bps | Higher fill rate |

## Stakeholders / Owners

| Name | Team/Org | Role | Note |
| :---- | :---- | :---- | :---- |
| Pickle Rick | Engineering | Lead Architect | Implementation Lead |
| ScalaSpeicher | Quant | Trading Lead | Validation |
