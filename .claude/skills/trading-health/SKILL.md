---
name: trading-health
description: Check trading engine, Bittensor validator, and bridge health status
---

Run these health checks and summarize the results concisely:

1. **Trading engine health**: `curl -s -H "X-API-Key: local-validator-dev" http://localhost:8080/health`
2. **Bittensor status**: `curl -s -H "X-API-Key: local-validator-dev" http://localhost:8080/api/bittensor/status`
3. **Docker containers**: `docker compose ps`

Summarize: which services are up/down, any warnings, bridge sync status, and last successful poll time.
