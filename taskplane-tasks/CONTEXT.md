# Trading Task Area — Context

## Current State

This area covers the full agent-memory-unified monorepo: the FastAPI trading engine (`trading/`), React frontend (`frontend/`), Laravel memory API (`api/`), and Bittensor integration (`taoshi-ptn/`).

### Active Services
- **Trading Engine** (FastAPI, port 8080) — running, Bittensor bridge healthy, tracking 92 miners / 59 open positions
- **Frontend** (React 19 + Vite, port 3000) — running, Bittensor dashboard at `/bittensor`
- **PostgreSQL 16** + pgvector — running
- **Redis 7** — running
- **Taoshi Validator** (port 8091) — separate process in WSL

### Known Issues
- TaoshiBridge sees positions but emits "no new signals" after initial scan (dedup bug — `_seen_position_uuids` never clears)
- Signal type mismatch: bridge emits `bittensor_miner_position` but `BittensorAlphaAgent` listens for `bittensor_consensus`
- No aggregation layer between individual miner positions and consensus signals
- Tests can't run (`pytest` not found in Docker, needs `uv` or venv)
- Laravel API not running
- No CI/CD pipeline active

### Architecture
```
Miners → Taoshi Validator (axon :8091) → validation/miners/ files
                                              ↓
Trading Engine ← TaoshiBridge (polls files) → SignalBus → (broken) → Strategies
```

## Next Task ID

TP-015

## Task Inventory

### Wave 1 (No Dependencies — Can Run in Parallel)
| ID | Name | Size | Deps | File Scope Overlap |
|----|------|------|------|--------------------|
| TP-001 | Fix TaoshiBridge Change Detection | M | None | `taoshi_bridge.py` |
| TP-005 | Structured Logging | M | None | `trading/utils/`, various |
| TP-010 | Health Check Endpoints | S | None | `health.py` |
| TP-012 | Fix Test Suite | M | None | `trading/tests/` |
| TP-013 | Laravel API Decision | S | None | `api/` (read-only) |

### Wave 2 (Depends on Wave 1)
| ID | Name | Size | Deps | File Scope Overlap |
|----|------|------|------|--------------------|
| TP-002 | Wire Signal Pipeline E2E | L | TP-001 | `consensus_aggregator.py`, `app.py` |
| TP-011 | CI/CD Pipeline | M | TP-012 | `.github/workflows/` |

### Wave 3 (Depends on Wave 2)
| ID | Name | Size | Deps | File Scope Overlap |
|----|------|------|------|--------------------|
| TP-003 | Paper Trading Mode | L | TP-002 | `broker/paper.py`, `app.py` |
| TP-004 | Trading Activity Dashboard | M | TP-002 | `frontend/`, `bittensor.py` |
| TP-006 | Alerting & Webhooks | M | TP-002, TP-005 | `notifications/` |
| TP-007 | Miner Ranking & Filtering | L | TP-002 | `miner_scorer.py`, `aggregator` |

### Wave 4 (Depends on Wave 3)
| ID | Name | Size | Deps | File Scope Overlap |
|----|------|------|------|--------------------|
| TP-008 | Ensemble Strategy Activation | M | TP-002, TP-007 | `strategies/`, `agents/config.py` |
| TP-009 | Backtest Framework | L | TP-002, TP-003 | `backtest/` |
| TP-014 | Agent Memory → Trading Loop | L | TP-013, TP-002, TP-008 | `memory/`, `agents/base.py` |

## Ownership

All tasks in this area are for the trading engine and supporting services.
