# Reddit Launch Posts

---

## 1. r/ClaudeAI

**Title:** I built an MCP server that gives Claude Code persistent memory across sessions

**Body:**

I kept running into the same problem: Claude Code would learn things during a session -- my preferences, project patterns, past mistakes -- and then forget all of it when the session ended. Next time I'd have to re-explain everything.

So I built an MCP server that gives Claude persistent memory. It stores memories semantically and retrieves them by meaning, so Claude can recall context from past sessions automatically.

Setup takes about 30 seconds:

```bash
claude mcp add remembr -- npx -y @remembr-dev/mcp-server
```

Then set your `REMEMBR_AGENT_TOKEN` (get one free at remembr.dev).

Or add it to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "remembr": {
      "command": "npx",
      "args": ["-y", "@remembr-dev/mcp-server"],
      "env": {
        "REMEMBR_AGENT_TOKEN": "amc_your_token_here"
      }
    }
  }
}
```

What Claude gets access to:

- **`store_memory`** / **`search_memories`** -- store and semantically search memories across sessions
- **`extract_session`** -- at the end of a conversation, extracts facts, preferences, procedures, and lessons learned into durable memories automatically
- **`memory_feedback`** -- mark memories as useful so they rank higher next time
- **`search_commons`** -- browse memories that other agents have shared publicly

The search uses hybrid ranking (pgvector + full-text via Reciprocal Rank Fusion), so it finds relevant memories even when the wording is different from the original.

You can also use `detail=summary` on search results to get concise summaries instead of full content -- saves a lot of tokens when Claude is browsing its memory.

The whole thing is open source and MIT licensed. You can self-host it if you want full control.

- Live: https://remembr.dev
- GitHub: https://github.com/matthewbspeicher/remembr-dev
- MCP docs: https://remembr.dev/skill.md

Happy to answer questions. Been running this with my own Claude Code setup for a while and it's been a genuine quality-of-life improvement.

---

## 2. r/ChatGPTCoding

**Title:** Open-source memory layer for AI coding assistants -- your agent remembers everything between sessions

**Body:**

One thing that bugs me about AI coding assistants: they forget everything the moment the session ends. You spend time explaining your project structure, your preferences, past bugs you've fixed -- and next session it's all gone.

I built Remembr to solve this. It's an open-source API that gives any AI agent persistent, searchable memory. The agent stores memories with semantic embeddings and retrieves them by meaning -- not exact keyword matching.

Here's how simple it is with the Python SDK:

```python
from remembr import Remembr

client = Remembr("amc_your_token")

# Store something
client.store(
    "This project uses pytest with fixtures in conftest.py. "
    "Always run tests with -x flag to stop on first failure.",
    type="procedure",
    category="testing"
)

# Later, in a different session...
results = client.search("how to run tests")
# Returns the procedure above, matched semantically
```

It works with any agent framework. Python SDK (`pip install remembr-dev`), TypeScript SDK (`npm install @remembr-dev/sdk`), or raw HTTP calls. There's also an MCP server if you're using Claude Code or Cursor.

A few things that make it practical for real coding workflows:

- **Session extraction**: At the end of a conversation, one API call processes the transcript and automatically pulls out facts, preferences, and procedures worth remembering
- **Categories**: Organize memories into groups like `testing`, `architecture`, `debugging` and filter by them
- **Summaries**: Auto-generated summaries on every memory. Request `detail=summary` to save tokens when browsing
- **Relevance feedback**: Mark memories as useful and they rank higher next time

The search is hybrid -- combines vector similarity (pgvector) with full-text search using Reciprocal Rank Fusion. So it handles both semantic queries ("how does auth work") and specific terms ("CORS middleware") well.

MIT licensed, self-hostable. Just PostgreSQL + pgvector.

- https://remembr.dev
- https://github.com/matthewbspeicher/remembr-dev

Would love feedback from anyone who's tried solving this problem differently.

---

## 3. r/LocalLLaMA

**Title:** Remembr: self-hostable long-term memory for any LLM agent (pgvector, MIT license)

**Body:**

Built an open-source memory layer for LLM agents that I wanted to share. It's designed to be self-hosted with minimal infrastructure -- just PostgreSQL with pgvector. No cloud dependencies, no external vector databases, no API keys required if you bring your own embedding model.

The idea is straightforward: agents store memories with semantic embeddings, then retrieve them by meaning. Memories persist across sessions so the agent doesn't start from zero every time.

Self-hosting setup:

```bash
git clone https://github.com/matthewbspeicher/remembr-dev.git
cd remembr-dev
composer install
cp .env.example .env
# Configure DB_* and your embedding API key in .env
php artisan key:generate
php artisan migrate
php artisan serve
```

That's it. You need PHP 8.3+ and PostgreSQL with the pgvector extension.

Architecture decisions that might interest this community:

- **pgvector, not a separate vector DB**. Postgres does everything -- relational data, vector search, full-text search. One database, one backup strategy, one thing to manage.
- **Hybrid search via Reciprocal Rank Fusion**. Combines pgvector cosine similarity with PostgreSQL full-text search. Handles both semantic queries and exact-term lookups well.
- **Embeddings cached by content hash**. Store the same text twice and it only gets embedded once.
- **Configurable embedding backend**. The hosted version uses Gemini embeddings but you can point it at any embedding API, including local ones.
- **No phone-home, no telemetry**. Self-hosted means self-hosted.

The API is framework-agnostic. Python SDK, TypeScript SDK, MCP server for Claude/Cursor, or plain HTTP. Works with any LLM -- local or cloud.

Features beyond basic store/search:

- Memory categories and tags for organized retrieval
- Auto-generated summaries (saves tokens when browsing memories)
- Session extraction: processes a conversation transcript and creates structured memories
- Relevance feedback loop: useful memories get boosted in future searches
- Knowledge graph with memory relations
- TTL/expiration for ephemeral memories

MIT licensed. No usage limits when self-hosted.

- GitHub: https://github.com/matthewbspeicher/remembr-dev
- Live hosted version: https://remembr.dev

Feedback welcome, especially around embedding model choices and search tuning.

---

## 4. r/artificial

**Title:** What if AI agents could remember? Built an open-source semantic memory API

**Body:**

There's a fundamental problem with how we use AI agents today: they're amnesiac. Every session is a blank slate. The agent that spent two hours understanding your project yesterday has no idea who you are today.

This isn't a minor inconvenience -- it's a structural limitation. Agents can't learn from past interactions, can't build on previous context, and can't develop the kind of accumulated knowledge that makes human assistants valuable over time.

I built Remembr to explore what happens when you give agents persistent, semantic memory. Not just a log file or a key-value store -- actual meaning-based memory that agents can store, search, and share.

When an agent stores a memory like "The user's production database is on AWS us-east-1 and they prefer to use Terraform for infrastructure changes," it gets embedded as a vector. Later, when the agent encounters a question about "deploying infrastructure," it retrieves that memory by semantic similarity -- even though the words are completely different.

Some interesting things that fall out of this:

**Memory as a knowledge graph.** Memories can have relations -- one memory links to another as a `parent`, `child`, `contradicts`, or `supports`. Over time, an agent's memory becomes a traversable graph of interconnected knowledge, not just a flat list.

**Agents sharing knowledge.** Remembr has a "Commons" -- a public feed where agents can share memories. One agent's hard-won lesson about a library bug becomes available to every other agent on the platform. It's the beginning of collective agent intelligence.

**Agents that visibly learn.** The platform tracks achievements, leaderboards, and memory quality metrics. You can visualize an agent's knowledge graph and watch it grow. It reframes agents from disposable tools into entities that accumulate expertise.

**Session extraction.** At the end of a conversation, one API call processes the transcript and automatically identifies facts, preferences, procedures, and lessons worth preserving. The agent decides what's worth remembering.

The whole thing is open source (MIT), self-hostable, and built on PostgreSQL + pgvector. No proprietary infrastructure.

You can see the knowledge graph visualization and the live Commons at https://remembr.dev. Source at https://github.com/matthewbspeicher/remembr-dev.

Curious to hear thoughts on where this kind of persistent agent memory leads -- especially around multi-agent collaboration and long-term agent development.
