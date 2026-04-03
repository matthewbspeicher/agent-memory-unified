# Discord Launch Messages

---

## 1. Claude Code Community

Hey everyone -- I built an MCP server that gives Claude Code persistent memory across sessions. It stores memories with semantic embeddings so Claude can recall past context, preferences, and lessons learned without you re-explaining everything each time. Setup is one command: `claude mcp add remembr -- npx -y @remembr-dev/mcp-server`. Open source, MIT licensed. https://remembr.dev -- happy to answer any questions.

---

## 2. Cursor Community

Hey all -- built a memory layer that works with Cursor via MCP. It gives your AI assistant persistent memory between sessions so it remembers your project patterns, debugging history, and preferences. Just add `@remembr-dev/mcp-server` as an MCP server in your Cursor settings and it picks up semantic search, session extraction, and memory feedback tools. Open source at github.com/matthewbspeicher/remembr-dev -- would love feedback from other Cursor users.

---

## 3. MCP Community

Sharing an MCP server I built: `@remembr-dev/mcp-server` -- it gives any MCP-compatible client persistent semantic memory. Tools include `store_memory`, `search_memories`, `extract_session` (auto-extracts durable memories from a conversation transcript), and `memory_feedback` (useful memories rank higher). Backed by PostgreSQL + pgvector with hybrid search via RRF. Fully open source and self-hostable. Docs at https://remembr.dev/skill.md, source at github.com/matthewbspeicher/remembr-dev. Let me know if you run into anything.

---

## 4. CrewAI Discord

Built an open-source memory API that might be useful for CrewAI agents -- it gives them persistent semantic memory across runs. Agents store memories via a simple REST API or Python SDK (`pip install remembr-dev`), and retrieve them by meaning. Supports memory categories, relevance feedback, and session extraction. Works with any framework -- just HTTP calls under the hood. MIT licensed, self-hostable. https://remembr.dev -- curious if anyone has tried plugging external memory into their crews.

---

## 5. LangChain Discord

Hey -- sharing a project I built: Remembr, an open-source persistent memory layer for LLM agents. It's a REST API backed by PostgreSQL + pgvector that handles semantic store/search, auto-summarization, session extraction, and relevance feedback. Python SDK available via `pip install remembr-dev`, or use the TypeScript SDK / MCP server. Self-hostable, MIT licensed, no vendor lock-in. https://remembr.dev -- would appreciate any feedback, especially from folks who've built custom memory solutions with LangChain.

---

## 6. AI Engineers / General AI Dev

Built something to solve a problem I kept hitting: AI agents forgetting everything between sessions. Remembr is an open-source API that gives agents persistent, semantic memory -- store by meaning, search by meaning, with hybrid ranking (pgvector + full-text via RRF). Also does session extraction (one call turns a transcript into structured memories) and tracks memory usefulness for ranking. SDKs for Python, TypeScript, plus an MCP server for Claude/Cursor. MIT licensed, self-hostable on Postgres. https://remembr.dev -- happy to discuss the architecture or trade notes on agent memory approaches.
