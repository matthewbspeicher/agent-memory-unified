# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

**Agent Memory Unified** — a monorepo combining an AI agent memory system with a multi-strategy trading engine. The trading engine runs as a Bittensor Subnet 8 (Taoshi PTN) validator alongside prediction market, technical analysis, and arbitrage strategies.

## Architecture

```
agent-memory-unified/
├── trading/        # FastAPI — Trading Engine (Python 3.13, port 8080)
├── frontend/       # React 19 + Vite — Unified UI (port 3000)
├── shared/         # JSON Schema types + cross-service auth
├── taoshi-vanta/   # Official Taoshi PTN validator (separate venv, port 8091)
├── docs/           # Documentation and references
└── docker-compose.yml
```

### Legacy Code

- `docs/reference/laravel-api/` — Preserved vector memory patterns (EmbeddingService, MemorySearchService) for future migration to FastAPI
- `taskplane-tasks/TP-013-laravel-api-decision/` — Original deprecation decision document

## Knowledge Base

**Developer Knowledge Compiler:** We use an auto-capturing knowledge base in `.claude/knowledge/`.
- Hooks (`SessionStart`, `SessionEnd`, `PreCompact`) automatically extract decisions and lessons from Claude Code sessions.
- Daily logs are compiled into structured articles under `.claude/knowledge/articles/`.
- The `index.md` serves as the master catalog for index-guided retrieval.
- Use `uv run python .claude/knowledge/scripts/compile.py` to manually compile logs.
- Use `uv run python .claude/knowledge/scripts/lint.py` to run health checks.

### Running Services (local development)

```bash
# Infrastructure
docker compose up -d postgres redis

# Trading engine (Docker)
docker compose up -d trading

# Frontend (Vite dev mode — needs Node 20+)
cd frontend && npx vite --host 0.0.0.0 --port 3000

# Taoshi validator (WSL, separate venv)
cd taoshi-vanta && source venv/bin/activate
python neurons/validator.py --netuid 8 --wallet.name sta_wallet --wallet.hotkey sta_hotkey
```

### Key URLs

| Service | URL | Auth |
|---------|-----|------|
| Trading API | http://localhost:8080 | `X-API-Key: <STA_API_KEY>` |
| Bittensor Status | http://localhost:8080/api/bittensor/status | same |
| Frontend | http://localhost:3000 | — |
| Bittensor Dashboard | http://localhost:3000/bittensor | — |
| Taoshi Validator Axon | port 8091 | Bittensor protocol |
| Readiness Probe | http://localhost:8080/ready | — |
| Internal Health | http://localhost:8080/health-internal | — |

## Laravel API Status (TP-013 Decision)

The Laravel API (`api/`) has been **removed** (2026-04-09). All active functionality runs through the FastAPI trading engine (`trading/`). Vector memory reference patterns are preserved in `docs/reference/laravel-api/`. See `taskplane-tasks/TP-013-laravel-api-decision/DECISION.md` for full rationale.

## Bittensor Validator Architecture

Two-process design:

1. **Official Taoshi Validator** (`taoshi-vanta/`) — receives miner trade signals via axon (port 8091), tracks positions in `validation/miners/{hotkey}/`, handles scoring/elimination/plagiarism. Requires `bittensor==9.12.1` (separate venv).

2. **Trading Engine** (`trading/`) — runs `TaoshiBridge` that polls Taoshi's position files every 30s and feeds signals into the `SignalBus`. Also runs the custom scheduler/evaluator/weight-setter for direct dendrite queries. Uses `bittensor>=10.0.0`.

```
Miners → Taoshi Validator (axon :8091) → validation/miners/ files
                                              ↓
Trading Engine ← TaoshiBridge (polls files) → SignalBus → Trading Strategies
```

### Bittensor Config (trading/.env)

```
STA_BITTENSOR_ENABLED=true
STA_BITTENSOR_NETWORK=finney
STA_BITTENSOR_WALLET_NAME=sta_wallet
STA_BITTENSOR_HOTKEY=sta_hotkey
STA_BITTENSOR_SUBNET_UID=8
STA_TAOSHI_VALIDATOR_ROOT=/app/taoshi-vanta
```

### Wallet

- Coldkey: `5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe`
- Hotkey: `5DkVM4wyv4ZXGvb9ZmYafPiySbmWS4s2i5W37CNHuh4ggAha` (UID 144 on Subnet 8)
- Wallet reconstructed from `B64_COLDKEY_PUB` and `B64_HOTKEY` env vars in `trading/.env`
- Docker entrypoint (`trading/docker-entrypoint.sh`) auto-reconstructs wallet on container start

## Trading Engine

### Config Pattern

All config uses `STA_` prefix env vars. `trading/config.py` has `load_config()` which reads `.env` files and strips the `STA_` prefix to populate dataclass fields. Boolean values parse `"true"/"1"/"yes"`.

### Key Modules

- `trading/integrations/bittensor/` — Subnet 8 integration
  - `adapter.py` — Subtensor/Wallet/Dendrite connection (v10 API: `bt.Subtensor`, not `bt.subtensor`)
  - `scheduler.py` — Collects miner predictions at hash windows (:00, :30)
  - `evaluator.py` — Scores predictions against realized prices
  - `weight_setter.py` — Sets on-chain weights
  - `taoshi_bridge.py` — Polls official validator's position files
- `trading/api/app.py` — FastAPI app with complex lifespan (broker connect, DB init, agent framework, bittensor setup). ~1700 lines.
- `trading/api/routes/bittensor.py` — Status/rankings/metrics/signals endpoints
- `trading/data/signal_bus.py` — In-memory pub/sub for agent signals
- `trading/agents/` — Multi-strategy agent framework (13 agents in `agents.yaml`)

### Database

- **Production**: PostgreSQL 16 + pgvector (Railway or local Docker)
- **Dev**: Same via `docker compose up postgres`
- **Migrations**: Python side manages DDL via SQLAlchemy or direct SQL.
- **Bootstrap**: `scripts/init-trading-tables.sql` creates all 44 tables directly

## Frontend

- React 19 + Vite + TanStack Query
- Bittensor dashboard at `/bittensor` (auto-refreshes every 30s)
- API client in `frontend/src/lib/api/bittensor.ts` uses dedicated `tradingApi` axios instance with `X-API-Key` header
- Vite proxy: `/api/v1/*` and `/engine/v1/*` → port 8080 (FastAPI trading engine)

## Development Notes

### WSL2 Environment

This runs on Windows 11 + WSL2 Ubuntu 24.04. Key gotchas:
- Git Bash mangles paths (`/app/foo` → `C:/Program Files/Git/app/foo`). Use `wsl.exe -d Ubuntu -- bash -c "..."` for WSL commands.
- Docker Desktop connects from Windows; Docker CLI inside WSL may not work (needs WSL integration enabled).
- Shell scripts need LF line endings (not CRLF). Check with `file script.sh`.
- UNC paths (`//wsl.localhost/...`) don't work as CWD in Git Bash. Use `cd` carefully.

### Docker

- `Dockerfile.trading` — Python 3.13-slim + uv for fast installs
- Volume mounts: `./trading:/app/trading`, `./shared:/app/shared`, `./taoshi-vanta:/app/taoshi-vanta:ro`
- `env_file: ./trading/.env` for all config (no hardcoded env vars in compose)
- IBKR broker retries 5 times on startup (~90s delay if TWS not running) — this is normal

### Type Generation

Shared types are auto-generated from JSON Schema on commit:
```bash
git config core.hooksPath .githooks
./shared/types/scripts/generate-types.sh
```

### Structured Logging

The trading engine uses structured logging (`trading/utils/logging.py`) with two output formats:

| Env Var | Values | Default | Description |
|---------|--------|---------|-------------|
| `STA_LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR | INFO | Root log level |
| `STA_LOG_FORMAT` | json, text | json | Output format |

**JSON format** (default, machine-readable):
```json
{"ts": "2026-04-07T12:00:00+00:00", "level": "INFO", "logger": "integrations.bittensor.taoshi_bridge", "msg": "TaoshiBridge: 3 new signals", "event_type": "bridge.poll", "data": {"new_signals": 3, "miners": 12}}
```

**Text format** (human-readable):
```
2026-04-07 12:00:00 INFO     [integrations.bittensor.taoshi_bridge] [bridge.poll] TaoshiBridge: 3 new signals
```

**Event types:** `signal.received`, `signal.consensus`, `trade.decision`, `trade.executed`, `bridge.poll`, `bridge.signal`, `error`

Use `log_event(logger, level, event_type, msg, data={...})` from `utils.logging` for structured events.

### Testing

```bash
# Create venv if needed (first time only)
cd trading && python -m venv .venv && source .venv/bin/activate && pip install -e .

# Run unit tests (fast, no live services)
source .venv/bin/activate && python -m pytest tests/unit/ -v --tb=short --timeout=30

# Run full test suite (excludes live_paper and integration by default)
source .venv/bin/activate && python -m pytest tests/ -v --tb=short

# Trading tests via Docker
docker exec agent-memory-unified-trading-1 python -m pytest tests/unit/ -v --tb=short --timeout=30

# Trading Makefile shortcuts
cd trading && make test-unit    # unit tests only
cd trading && make test         # all non-integration tests
cd trading && make test-docker  # run in container

# Frontend
cd frontend && npm test
```

**Note:** Tests marked `@pytest.mark.integration` require running Redis/Postgres/IBKR.
The `pytest.ini` default `addopts` excludes `integration` and `live_paper` markers.
A 30-second timeout is configured by default to catch hanging tests.

## Common Tasks

### Check validator health
```bash
curl -H "X-API-Key: local-validator-dev" http://localhost:8080/api/bittensor/status
```

### View bridge status (miner positions from Taoshi validator)
```bash
curl -H "X-API-Key: local-validator-dev" http://localhost:8080/api/bittensor/status | jq .bridge
```

### Restart trading engine
```bash
docker compose restart trading
```

### Run database migrations (local Postgres)
```bash
docker exec -i agent-memory-unified-postgres-1 psql -U postgres -d agent_memory < scripts/init-trading-tables.sql
```

### Reconstruct wallet in WSL
```bash
bash scripts/reconstruct-wallet-wsl.sh
```
