# Research: opencode-mem vs agent-memory-unified Memory Systems

## Executive Summary

This research compares the **opencode-mem** plugin (TypeScript/Bun) with our current **agent-memory-unified** memory system (Python/Claude Agent SDK). While both aim to provide persistent memory for AI agents, they take fundamentally different approaches to storage, retrieval, and user experience.

**Key Finding:** The systems are complementary rather than competitive. Our file-based approach excels at structured knowledge management, while opencode-mem's vector database approach offers superior semantic search and scalability.

---

## Architecture Comparison

### Current System (agent-memory-unified)

| Aspect | Implementation |
|--------|----------------|
| **Location** | `.claude/knowledge/` |
| **Technology** | Python 3.12+ + Claude Agent SDK |
| **Storage** | Markdown files with wikilinks |
| **Retrieval** | Index-guided (LLM reads structured index) |
| **Scale Design** | 50-500 articles (index-guided) |
| **UI** | CLI scripts only |
| **Auto-Capture** | Hook-based (SessionStart, SessionEnd, PreCompact) |

**Architecture:**
```
.claude/knowledge/
├── daily/          # Immutable conversation logs (source)
├── knowledge/      # Compiled knowledge articles (executable)
│   ├── index.md    # Master catalog
│   ├── concepts/   # Atomic knowledge
│   ├── connections/ # Cross-cutting insights
│   └── qa/         # Filed query answers
├── scripts/        # CLI tools (compile.py, query.py, lint.py, flush.py)
└── hooks/          # Claude Code hooks
```

**Key Philosophy:** Compiler analogy - daily/ = source code, LLM = compiler, knowledge/ = executable

### External System (opencode-mem)

| Aspect | Implementation |
|--------|----------------|
| **Location** | npm package (`opencode-mem`) |
| **Technology** | TypeScript/Bun + OpenCode Plugin SDK |
| **Storage** | SQLite + USearch vector database |
| **Retrieval** | Vector similarity search + embeddings |
| **Scale Design** | Scales to larger datasets via vector search |
| **UI** | Full web UI at http://127.0.0.1:4747 |
| **Auto-Capture** | Plugin hooks (chat.message, session.compacted, session.idle) |

**Architecture:**
```
opencode-mem/
├── src/
│   ├── index.ts           # Main plugin entry
│   ├── services/
│   │   ├── client.ts      # Memory client
│   │   ├── auto-capture.ts # Automatic capture
│   │   ├── user-memory-learning.ts # User profile learning
│   │   ├── web-server.ts  # Web UI server
│   │   ├── sqlite/        # SQLite database layer
│   │   └── vector-backends/ # Vector indexing (USearch + ExactScan)
│   └── web/               # Web UI components
└── config: ~/.config/opencode/opencode-mem.jsonc
```

**Key Philosophy:** Vector-first semantic search with automatic user profile learning

---

## Feature Comparison Matrix

| Feature | agent-memory-unified | opencode-mem | Recommendation |
|---------|---------------------|--------------|----------------|
| **Storage Format** | Markdown files | SQLite + vectors | Keep markdown, add vector index |
| **Retrieval Method** | Index-guided | Vector similarity | Hybrid: index + vector |
| **Search Quality** | Good for known topics | Excellent for discovery | Add vector search |
| **Scalability** | 50-500 articles | 1000s+ articles | Add vector for scale |
| **User Interface** | CLI only | Full web UI | Add web UI |
| **Auto-Capture** | Session hooks | Plugin hooks + idle | Add idle capture |
| **User Profiles** | Not implemented | Automatic learning | Add user profiling |
| **Privacy** | Not implemented | Built-in protection | Add privacy layer |
| **Deduplication** | Manual | Vector-based | Add smart dedup |
| **Multi-Provider** | Claude only | OpenAI, Anthropic, local | Add provider options |
| **Configuration** | Environment vars | JSONC config file | Add JSONC config |
| **Memory Injection** | Not implemented | On compaction/message | Add injection |

---

## Key Learnings to Incorporate

### 1. Vector Database Integration (High Priority)

**Current Gap:** Our system relies on LLM reading the entire index to find relevant articles. This works for 50-500 articles but doesn't scale.

**Learning from opencode-mem:** Use SQLite + USearch for vector indexing while keeping markdown as source of truth.

**Implementation Plan:**
```python
# Proposed hybrid architecture
.claude/knowledge/
├── knowledge/           # Keep existing markdown files
│   ├── index.md
│   ├── concepts/
│   ├── connections/
│   └── qa/
├── vectors/            # NEW: Vector index
│   ├── embeddings.db   # SQLite with USearch
│   └── metadata.json   # Article metadata
└── scripts/
    ├── compile.py      # Existing
    ├── query.py        # Enhanced with vector search
    └── vectorize.py    # NEW: Generate embeddings
```

**Benefits:**
- Semantic search for discovery ("find articles about authentication")
- Scales to 1000s of articles without LLM context bloat
- Keeps markdown files human-readable and editable

### 2. Web UI for Memory Browsing (Medium Priority)

**Current Gap:** No visual interface for browsing memories.

**Learning from opencode-mem:** Full web UI with timeline view and search.

**Implementation Plan:**
- Simple Flask/FastAPI server
- Timeline view of knowledge articles
- Search interface with vector similarity
- Article editor with wikilink support

### 3. Enhanced Auto-Capture (Medium Priority)

**Current Gap:** Only captures on session start/end/compact.

**Learning from opencode-mem:** Capture on idle, inject memories on compaction.

**Implementation Plan:**
- Add `session.idle` hook (5min inactivity)
- Implement memory injection during compaction
- User profile learning from conversation patterns

### 4. User Profile Learning (Low Priority)

**Current Gap:** No user preference/behavior tracking.

**Learning from opencode-mem:** Automatic user profile building.

**Implementation Plan:**
- Track frequently discussed topics
- Learn user preferences and patterns
- Store in `knowledge/profiles/` directory

### 5. Privacy Protection (Medium Priority)

**Current Gap:** No filtering of sensitive content.

**Learning from opencode-mem:** Strip private content before storage.

**Implementation Plan:**
- Add PII detection in compile.py
- Configurable privacy rules
- Separate private vs public knowledge bases

### 6. Smart Deduplication (Medium Priority)

**Current Gap:** Manual deduplication required.

**Learning from opencode-mem:** Vector-based similarity detection.

**Implementation Plan:**
- Vector similarity threshold (0.85+)
- Automatic merge suggestions
- Duplicate detection during compile

### 7. Multi-Provider Support (Low Priority)

**Current Gap:** Locked to Claude API.

**Learning from opencode-mem:** Support OpenAI, Anthropic, local models.

**Implementation Plan:**
- Abstract LLM interface
- Support multiple providers
- Local embedding models option

---

## Implementation Roadmap

### Phase 1: Foundation (1-2 weeks)
1. **Vector Database Setup**
   - Add SQLite + USearch dependencies
   - Create vectorize.py script
   - Generate embeddings for existing articles

2. **Enhanced Query System**
   - Hybrid search: index + vector
   - Update query.py with vector search
   - Add similarity scoring

### Phase 2: User Experience (2-3 weeks)
1. **Web UI**
   - Simple Flask server
   - Timeline view
   - Search interface
   - Article editor

2. **Enhanced Auto-Capture**
   - Session idle detection
   - Memory injection on compaction
   - User profile tracking

### Phase 3: Advanced Features (3-4 weeks)
1. **Privacy & Deduplication**
   - PII detection
   - Smart deduplication
   - Privacy rules configuration

2. **Multi-Provider Support**
   - Abstract LLM interface
   - Provider configuration
   - Local model support

---

## Technical Recommendations

### 1. Keep Markdown as Source of Truth
Don't replace markdown files with database. Use vectors as an index layer only.

### 2. Hybrid Retrieval Strategy
```
User Query → Vector Search (discovery) + Index Search (known topics) → LLM Synthesis
```

### 3. Incremental Vectorization
Only re-embed changed articles, not the entire corpus.

### 4. Configuration-Driven
Add `.claude/knowledge/config.json` for:
- Vector search settings
- Privacy rules
- Provider configuration
- UI settings

### 5. Backward Compatibility
Ensure all existing scripts continue to work. Vector search is additive, not replacement.

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Vector DB complexity** | Medium | Use simple SQLite + USearch, not complex DB |
| **Performance overhead** | Low | Incremental updates, caching |
| **Storage growth** | Low | Markdown files unchanged, vectors are small |
| **Breaking changes** | High | Maintain backward compatibility |
| **Privacy concerns** | Medium | Add privacy layer before storage |

---

## Conclusion

The opencode-mem plugin offers valuable insights for enhancing our memory system, particularly in:
1. **Vector search** for semantic discovery
2. **Web UI** for better user experience
3. **Auto-capture** improvements
4. **Privacy and deduplication**

However, our file-based approach has advantages:
1. **Human-readable** knowledge articles
2. **Git-friendly** version control
3. **Obsidian-compatible** with wikilinks
4. **Simple architecture** without complex dependencies

**Recommendation:** Adopt a hybrid approach - keep markdown files as source of truth, add vector indexing for search, and implement a simple web UI. This combines the best of both systems while maintaining our existing strengths.

---

## Next Steps

1. **Prototype vector search** with existing knowledge base
2. **Design web UI** wireframes
3. **Plan auto-capture** enhancements
4. **Estimate implementation effort** for each phase

---

*Research completed: 2026-04-08*
*Sources: GitHub repository analysis, architecture review, feature comparison*