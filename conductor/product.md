# Initial Concept

Agent Memory Unified Monorepo - An AI agent memory system with autonomous trading capabilities, a shared PostgreSQL database, and a unified React dashboard.

## Vision
To provide a unified ecosystem for autonomous AI agents that seamlessly combines long-term memory capabilities with algorithmic trading. This platform serves as a personal workspace where quantized trading bots and intelligent agents can share state, persist memories in a vector database, and communicate in real-time.

## Target Audience
- **Quant Traders:** Individuals and small teams who want to build and manage autonomous trading bots with sophisticated memory and strategic recall.

## Core Goals
1. **Unified Ecosystem:** Create a cohesive platform where disparate services (Laravel for memory, FastAPI for trading) operate as a single, integrated system.
2. **Persistent Memory:** Enable agents to store and retrieve contextual information using a vector-enabled PostgreSQL database (`pgvector`).
3. **Real-Time Synergy:** Facilitate low-latency event-driven communication between the API and the trading engine using Redis Streams.
4. **Visual Insight:** Provide a powerful React-based dashboard, including a 3D Knowledge Graph, to monitor and manage the internal states of all agents and trades.

## Key Features
- **Vector Memory API:** A robust Laravel-based API providing persistent, searchable memory for AI agents using PostgreSQL + pgvector.
- **Redis Event Bus:** A cross-service event stream (Laravel -> Redis -> Python) for real-time synchronization and triggers.
- **Unified UI Dashboard:** A modern React 19 SPA featuring a central management interface for agents, memory logs, and trading performance.
- **Simulation & Validation:** A risk-free paper trading environment and historical backtesting engine to verify strategy performance before deployment.
- **Miner Performance & Ranking:** Automated accuracy-based scoring for Bittensor miners, enabling weighted consensus and institutional-grade signal validation.
- **Polyglot Monorepo:** A shared codebase architecture using JSON Schema for unified type definitions across PHP, Python, and TypeScript.

## Success Metrics
- **Seamless Integration:** All three services (API, Trading, Frontend) can be started and interact out of the box.
- **Memory Accuracy:** Agents can reliably retrieve relevant memories via the vector API to inform trading decisions.
- **System Stability:** High uptime for the background trading engine and event processing pipeline.
