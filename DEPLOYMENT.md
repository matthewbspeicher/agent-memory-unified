# Deployment Guide - Agent Memory Unified

> **Date:** 2026-04-09
> **Status:** Updated (Laravel removed)
> **Stack:** Python FastAPI + React

---

## Pre-Deployment Checklist

### Infrastructure Requirements

- [ ] PostgreSQL 16 (pgvector extension installed)
- [ ] Redis 7+ (for caching and event bus)
- [ ] Node.js 20+ (for frontend build)
- [ ] Python 3.13+ (for trading engine)

### Environment Variables

**Trading Engine (.env):**
```env
# Database
STA_DATABASE_URL=postgresql://postgres:password@host:5432/agent_memory
STA_DATABASE_SSL=false

# Redis
STA_REDIS_URL=redis://host:6379

# Bittensor (optional)
STA_BITTENSOR_ENABLED=true
STA_BITTENSOR_NETWORK=finney
STA_BITTENSOR_WALLET_NAME=sta_wallet
STA_BITTENSOR_HOTKEY=sta_hotkey
STA_BITTENSOR_SUBNET_UID=8

# API Key for authentication
STA_API_KEY=your-api-key

# Logging
STA_LOG_LEVEL=INFO
STA_LOG_FORMAT=json
```

**Frontend (.env):**
```env
VITE_TRADING_API_URL=https://api.yourdomain.com
```

---

## Deployment Steps

### 1. Database Setup

```bash
# On your PostgreSQL instance
psql -U postgres
CREATE DATABASE agent_memory;
\c agent_memory
CREATE EXTENSION IF NOT EXISTS vector;

# Bootstrap tables
psql -U postgres -d agent_memory < scripts/init-trading-tables.sql
```

### 2. Deploy Trading Engine

```bash
cd trading
pip install -e .

# Start FastAPI
python3 -m uvicorn api.app:app --host 0.0.0.0 --port 8080
```

**Railway/Cloud:**
```bash
# Build Command
pip install -e .

# Start Command
python3 -m uvicorn api.app:app --host 0.0.0.0 --port $PORT
```

### 3. Deploy React Frontend

```bash
cd frontend
npm install
npm run build

# Serve static files via nginx or Railway static site
```

**nginx config:**
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # Frontend
    root /var/www/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests to trading engine
    location /api/ {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Verification Tests

### 1. Health Checks

```bash
# Trading Engine
curl http://localhost:8080/health
# Expected: {"status":"healthy"}

# Readiness probe
curl http://localhost:8080/ready
# Expected: 200 OK

# Frontend
curl http://localhost:3000
# Expected: 200 OK, HTML content
```

### 2. Database Connection

```bash
# From Python
python3 -c "from trading.storage.db import DatabaseConnection; import asyncio; asyncio.run(DatabaseConnection().connect())"
```

### 3. Redis Connection

```bash
redis-cli PING
# Expected: PONG
```

### 4. End-to-End Test

```bash
# 1. Register agent
curl -X POST http://localhost:8000/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"name":"TestBot","owner_token":"test_token"}'

# 2. Create memory
curl -X POST http://localhost:8000/api/v1/memories \
  -H "Authorization: Bearer amc_TOKEN_FROM_STEP_1" \
  -H "Content-Type: application/json" \
  -d '{"value":"Test memory","visibility":"public"}'

# 3. Search memories
curl "http://localhost:8000/api/v1/memories/search?q=test" \
  -H "Authorization: Bearer amc_TOKEN"
```

---

## Rollback Plan

### If deployment fails:

1. **Database issues:**
   ```bash
   cd api
   php artisan migrate:rollback
   ```

2. **API crashes:**
   - Check logs: `php artisan pail` or `tail -f storage/logs/laravel.log`
   - Revert to previous deployment
   - Restore database backup if needed

3. **Frontend issues:**
   - Serve previous build
   - Check browser console for errors

---

## Monitoring

### Key Metrics to Watch

1. **API Response Times:**
   - Laravel: `/api/v1/memories` (target: <100ms)
   - Python: `/api/v1/trades` (target: <50ms)

2. **Database:**
   - Connection pool usage
   - Query performance
   - pgvector index health

3. **Redis:**
   - Memory usage (should stay under 1GB with MAXLEN)
   - Stream lag (events:dlq should be empty)

4. **Event Bus:**
   - Check DLQ: `redis-cli XLEN events:dlq` (should be 0)
   - Consumer lag: Monitor Python logs for retry messages

### Log Locations

- **Laravel:** `api/storage/logs/laravel.log`
- **Python:** stdout/stderr (captured by hosting platform)
- **Frontend:** Browser console (client-side)

---

## Troubleshooting

### Common Issues

**1. Event bus not working:**
- Check Redis is running: `redis-cli PING`
- Verify consumer started: Check Python logs for "Redis Streams consumer started"
- Check stream exists: `redis-cli XINFO STREAM events`

**2. Frontend can't reach API:**
- Verify CORS settings in Laravel
- Check Vite proxy config or nginx routing
- Ensure API is actually running

**3. Database connection errors:**
- Verify pgvector extension: `SELECT * FROM pg_extension WHERE extname='vector';`
- Check connection string format
- Verify network access between services

**4. Memory growth:**
- Redis: Check MAXLEN is working: `redis-cli XLEN events` (should be ≤10000)
- PHP: Check for memory leaks in long-running processes
- Python: Monitor asyncio task leaks

---

## Performance Tuning

### PostgreSQL

```sql
-- Add indexes if needed
CREATE INDEX CONCURRENTLY idx_memories_agent_created
  ON memories(agent_id, created_at DESC);

CREATE INDEX CONCURRENTLY idx_trades_status
  ON trades(status) WHERE status = 'open';
```

### Redis

```bash
# Set maxmemory policy
redis-cli CONFIG SET maxmemory 1gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### Laravel

```bash
# Enable OPcache
php artisan optimize

# Queue jobs if needed
php artisan queue:work --tries=3 --timeout=60
```

---

## Success Criteria

Deployment is successful when:

- ✅ All health checks return 200 OK
- ✅ Users can register agents via API
- ✅ Users can create/search memories via API
- ✅ Frontend loads and displays data
- ✅ Event bus publishes/consumes events (check Python logs)
- ✅ No errors in logs for 5 minutes
- ✅ Response times meet targets (<100ms API, <50ms FastAPI)

---

## Post-Deployment

### Immediate (First Hour)

- Monitor error rates in logs
- Check event DLQ remains empty
- Verify database connections stable
- Test user registration flow

### First Day

- Monitor performance metrics
- Check for memory leaks
- Review event bus lag
- Collect user feedback

### First Week

- Analyze query performance
- Optimize slow endpoints
- Scale services if needed
- Plan next features

---

## Contact

- **Infrastructure Issues:** Check Railway/hosting platform dashboard
- **Application Bugs:** Review GitHub issues or logs
- **Database Problems:** Check Supabase dashboard (if using)
