---
name: restart-stack
description: Restart trading development stack (postgres, redis, trading engine)
disable-model-invocation: true
---

Restart the development stack in the correct order:

1. Start infrastructure: `docker compose up -d postgres redis`
2. Wait for postgres to be healthy: `docker compose ps postgres` — confirm "healthy" status
3. Restart trading engine: `docker compose restart trading`
4. Wait ~10 seconds for the trading engine to initialize
5. Run health check: `curl -s -H "X-API-Key: local-validator-dev" http://localhost:8080/health`
6. Report which services are up and any errors
