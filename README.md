# Agent Memory — Unified Monorepo

AI agent memory system with trading capabilities. Python + TypeScript architecture with shared types.

## Structure

```
agent-memory/
├── trading/     # FastAPI (Trading Engine, port 8080)
├── frontend/    # React 19 + Vite (Unified UI, port 3000)
├── shared/      # JSON Schema types
└── docs/        # Documentation and references
```

## Quick Start

```bash
# Infrastructure
docker compose up -d postgres redis

# Trading engine
docker compose up -d trading

# Frontend
cd frontend && npx vite --host 0.0.0.0 --port 3000
```

## Development Workflow

**1. Setup (one-time after clone):**
```bash
git config core.hooksPath .githooks
```

**2. Edit JSON Schema:**
```bash
# Modify shared/types/schemas/agent.schema.json
```

**3. Regenerate types:**
```bash
./shared/types/scripts/generate-types.sh
```

Types are **auto-regenerated** on commit by the pre-commit hook. Manual generation is optional.

**4. Use in services:**
```python
# Python
from shared_types import Agent, Memory

# PHP
use AgentMemory\SharedTypes\Agent;

# TypeScript
import { Agent, Memory } from '@/types';
```

**5. Commit:**
```bash
git add shared/types/
git commit -m "feat: add new field to Agent schema"
# → Pre-commit hook auto-regenerates and stages types
```

## Type Generation

Types are auto-generated from JSON Schemas in `shared/types/schemas/`.

**Setup (one-time after clone):**
```bash
git config core.hooksPath .githooks
```

**Manual generation:**
```bash
./shared/types/scripts/generate-types.sh
```

**Usage:**
- Python: `from shared_types import Agent, Memory`
- TypeScript: `import { Agent, Memory } from '@/types'`

## Architecture

See `docs/architecture/monorepo.md` for design decisions.

## Migration Status

- [x] Phase 0: Python hardening (DI refactor)
- [x] Phase 1: Monorepo setup (current)
- [ ] Phase 2: Database consolidation
- [ ] Phase 3: Event bus (already complete in STA)
- [ ] Phase 4: Hybrid auth
- [ ] Phase 5: Frontend unification
- [ ] Phase 6: Integration & deployment

## Testing

```bash
# Python trading tests
cd trading && make test

# Frontend tests
cd frontend && npm test
```
