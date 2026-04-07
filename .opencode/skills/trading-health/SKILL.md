---
name: trading-health
description: Check trading engine, Bittensor validator, and bridge health status
version: 1.0.0
author: claude
type: skill
category: monitoring
tags:
  - health
  - trading
  - bittensor
  - monitoring
---

# Trading Health Skill

> **Purpose**: Check the health status of all trading services and report issues.

---

## What I Do

Verify the operational status of:
1. Trading engine health endpoint
2. Bittensor integration status
3. Docker container status
4. Bridge sync status

---

## How to Use Me

### Quick Start

```bash
# Check all health statuses
/trading-health
```

---

## Commands

### /trading-health /health-check

Run these health checks and summarize the results concisely:

1. **Trading engine health**: `curl -s -H "X-API-Key: local-validator-dev" http://localhost:8080/health`
2. **Bittensor status**: `curl -s -H "X-API-Key: local-validator-dev" http://localhost:8080/api/bittensor/status`
3. **Docker containers**: `docker compose ps`

### Output Format

Summarize:
- Which services are up/down
- Any warnings
- Bridge sync status (miners tracked, open positions)
- Last successful poll time

---

## Expected Endpoints

| Service | URL | Auth |
|---------|-----|------|
| Trading Health | http://localhost:8080/health | X-API-Key header |
| Bittensor Status | http://localhost:8080/api/bittensor/status | X-API-Key header |
| Readiness Probe | http://localhost:8080/ready | None |

---

## Key Metrics

From `/api/bittensor/status`:
- `bridge.miners_tracked` - Number of miners being monitored
- `bridge.open_positions` - Number of open positions
- `bridge.signals_emitted` - Signals emitted in current session
- `scheduler.last_successful_query` - Last query time
- `evaluator.miners_evaluated` - Miners evaluated

---

## Troubleshooting

### Trading Engine Down
- Check logs: `docker compose logs trading`
- Restart: `docker compose restart trading`

### Bridge Not Syncing
- Check if Taoshi validator is running
- Verify `/app/taoshi-ptn/validation/miners/` directory exists and has files

### Postgres Issues
- Verify postgres container: `docker compose ps postgres`
- Check postgres logs: `docker compose logs postgres`

---

## Notes

- Default API key for local development: `local-validator-dev`
- Run `/restart-stack` if services need to be restarted
- Bittensor status endpoint requires valid API key
