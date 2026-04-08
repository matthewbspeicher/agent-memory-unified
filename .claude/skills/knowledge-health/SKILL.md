# Knowledge Health Skill

Run the memory compiler's linting script to check for structural and semantic issues in the knowledge base.

## Usage

When you need to verify the health of the developer knowledge base, run:
```bash
cd /opt/agent-memory-unified/.claude/knowledge && uv run python scripts/lint.py
```

If you only want to run structural checks (free, skips LLM contradiction checks):
```bash
cd /opt/agent-memory-unified/.claude/knowledge && uv run python scripts/lint.py --structural-only
```

## Checks Performed
- **Broken links**: `[[wikilinks]]` pointing to missing articles
- **Orphan pages**: Articles with zero inbound links
- **Orphan sources**: Daily logs that haven't been compiled
- **Stale articles**: Source logs changed since last compilation
- **Missing backlinks**: Asymmetric links
- **Sparse articles**: Below 200 words
- **Contradictions**: Conflicting claims (if LLM enabled)
