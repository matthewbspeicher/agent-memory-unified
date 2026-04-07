---
name: restart-stack
description: Restart trading development stack (postgres, redis, trading engine)
version: 1.0.0
author: claude
type: skill
category: devops
tags:
  - docker
  - restart
  - infrastructure
---

# Restart Stack Skill

> **Purpose**: Restart the trading development stack in the correct order with health verification.

---

## What I Do

Restart the development stack ensuring proper startup order and health verification:
1. Start infrastructure services (postgres, redis)
2. Wait for services to be healthy
3. Restart the trading engine
4. Verify all services are up

---

## How to Use Me

### Quick Start

```bash
# Restart the entire stack
/restack
```

### Health Check

```bash
# Check if stack is healthy
/health
```

---

## Commands

### /restart-stack /restack

Restart the development stack:

1. Start infrastructure: `docker compose up -d postgres redis`
2. Wait for postgres to be healthy: `docker compose ps postgres` — confirm "healthy" status
3. Restart trading engine: `docker compose restart trading`
4. Wait ~10 seconds for the trading engine to initialize
5. Run health check: `curl -s -H "X-API-Key: local-validator-dev" http://localhost:8080/health`
6. Report which services are up and any errors

### Expected Output

Report:
- Which Docker containers are running
- Trading engine health status
- Any errors encountered

---

## Dependencies

Requires:
- Docker and docker-compose installed
- `docker-compose.yml` in project root
- API key configured in `.env`

---

## Notes

- Postgres typically takes 5-10 seconds to become healthy
- Trading engine takes ~10 seconds to initialize after restart
- If trading engine fails to start, check logs: `docker compose logs trading`
