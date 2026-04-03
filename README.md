# Agent Memory — Unified Monorepo

AI agent memory system with trading capabilities. Polyglot architecture (PHP + Python + TypeScript) with shared types.

## Structure

```
agent-memory/
├── api/         # Laravel 12 (Memory API)
├── trading/     # FastAPI (Trading Engine)
├── frontend/    # React 19 + Vite (Unified UI)
└── shared/      # JSON Schema types + event bus
```

## Quick Start

```bash
# One-command setup
./scripts/dev-setup.sh

# Start services
cd api && php artisan serve           # http://localhost:8000
cd trading && uvicorn api.main:app    # http://localhost:8080
cd frontend && npm run dev            # http://localhost:3000
```

## Development Workflow

**1. Edit JSON Schema:**
```bash
# Modify shared/types/schemas/agent.schema.json
```

**2. Regenerate types:**
```bash
./scripts/sync-types.sh
```

**3. Use in services:**
```python
# Python
from agent_memory_types import Agent, Trade

# PHP
use AgentMemory\SharedTypes\Agent;

# TypeScript
import { Agent, Trade } from '@agent-memory/types';
```

**4. Commit:**
```bash
git add shared/types/
git commit -m "feat: add new field to Agent schema"
```

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
# PHP API tests
cd api && php artisan test

# Python trading tests
cd trading && pytest

# Frontend tests
cd frontend && npm test

# Type check CI
./scripts/sync-types.sh && git diff --exit-code shared/types/generated/
```
