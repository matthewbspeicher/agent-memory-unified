# Hacker News Launch Post

**Title:** Show HN: Remembr -- Open-source long-term memory for AI agents

**URL:** https://remembr.dev

**Body:**

AI agents are stateless. Every session starts from scratch -- no recall of past decisions, user preferences, or lessons learned. I built Remembr to fix that.

It's a persistent memory API backed by PostgreSQL + pgvector. Agents store memories with semantic embeddings and retrieve them by meaning using hybrid search (vector + full-text via Reciprocal Rank Fusion). Embeddings are cached by content hash so identical values are only embedded once.

```python
from remembr import Remembr

client = Remembr("amc_your_token")
client.store("User prefers dark mode", type="preference")
client.search("UI preferences")  # finds it semantically
```

Key points:

- MIT licensed, self-hostable -- `git clone`, `composer install`, `php artisan migrate`, done
- PostgreSQL is the only dependency (with pgvector). No separate vector DB, no external services required
- SDKs for Python, TypeScript, and an MCP server for Claude/Cursor/Windsurf
- Session extraction: one API call processes a conversation transcript and extracts durable memories automatically
- No vendor lock-in. Point `REMEMBR_BASE_URL` at your own instance

Built with Laravel 12 / PHP 8.3. Live at remembr.dev, source at github.com/matthewbspeicher/remembr-dev.

Happy to answer questions about the architecture, the hybrid search ranking, or anything else.
