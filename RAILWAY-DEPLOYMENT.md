# Railway Deployment Status - Agent Memory Commons

> **Deployed:** 2026-04-06
> **Project:** hopeful-presence
> **Environment:** production

---

## Deployment Overview

**3 services deployed to Railway:**
1. **Laravel API** - Memory & Arena service
2. **Python FastAPI** - Trading bot service
3. **React Frontend** - Unified dashboard

**Project URL:** https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066

---

## Build Configurations

### API Service (Laravel)
- **Builder:** Nixpacks
- **Runtime:** PHP 8.3 + FrankenPHP + Octane
- **Build:** `composer install --no-dev --optimize-autoloader`
- **Start:** `php artisan octane:start --server=frankenphp --host=0.0.0.0 --port=$PORT`
- **Healthcheck:** `/api/v1/health`

### Trading Service (Python)
- **Builder:** Nixpacks
- **Runtime:** Python 3.14
- **Build:** `pip install -e .`
- **Start:** `python3 -m uvicorn api.app:app --host 0.0.0.0 --port $PORT`
- **Healthcheck:** `/health`

### Frontend Service (React)
- **Builder:** Nixpacks
- **Runtime:** Node.js 20
- **Build:** `npm install && npm run build`
- **Start:** `npx serve -s dist -l $PORT`

---

## Deployment IDs

| Service | Deployment ID |
|---------|---------------|
| API | `b9530a17-bcdc-4fcf-b3f0-011f8a06c19c` |
| Trading | `ce2fac1e-0039-4e57-a947-449117649020` |
| Frontend | `1d58aef5-6338-4644-800c-81945168efc9` |

---

## Build Logs

- **API:** https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066/service/a5e1e4b3-df9e-4a27-af33-a7be5ec06652?id=b9530a17-bcdc-4fcf-b3f0-011f8a06c19c
- **Trading:** https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066/service/a5e1e4b3-df9e-4a27-af33-a7be5ec06652?id=ce2fac1e-0039-4e57-a947-449117649020
- **Frontend:** https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066/service/a5e1e4b3-df9e-4a27-af33-a7be5ec06652?id=1d58aef5-6338-4644-800c-81945168efc9

---

## Monitoring Commands

### Check Status
```bash
# API status
cd api && railway service status

# Trading status
cd trading && railway service status

# Frontend status
cd frontend && railway service status
```

### View Logs
```bash
# API logs
cd api && railway logs

# Build logs
cd api && railway logs --build

# Deployment logs
cd api && railway logs --deployment
```

### Open Dashboard
```bash
railway open
```

### Monitor Script
```bash
./monitor-railway.sh
```

---

## Environment Variables Needed

### API Service
```env
APP_ENV=production
APP_DEBUG=false
APP_KEY=base64:...  # Generate with: php artisan key:generate --show

DB_CONNECTION=pgsql
DB_HOST=${{Postgres.PGHOST}}
DB_PORT=${{Postgres.PGPORT}}
DB_DATABASE=${{Postgres.PGDATABASE}}
DB_USERNAME=${{Postgres.PGUSER}}
DB_PASSWORD=${{Postgres.PGPASSWORD}}

REDIS_HOST=${{Redis.REDIS_HOST}}
REDIS_PORT=${{Redis.REDIS_PORT}}
REDIS_PASSWORD=${{Redis.REDIS_PASSWORD}}

GEMINI_API_KEY=your-gemini-key
```

### Trading Service
```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
LOG_LEVEL=INFO
JWT_SECRET=your-256-bit-secret
```

### Frontend Service
```env
VITE_API_URL=https://your-api-domain.railway.app
```

---

## Post-Deployment Checklist

- [ ] Add PostgreSQL service: `railway add --service postgres`
- [ ] Add Redis service: `railway add --service redis`
- [ ] Set environment variables (see above)
- [ ] Run migrations: `railway run php artisan migrate --force`
- [ ] Generate app key: `railway run php artisan key:generate`
- [ ] Test health endpoints
- [ ] Configure custom domains
- [ ] Set up monitoring/alerts

---

## Custom Domains

To add custom domains:

```bash
# API domain
cd api
railway domain

# Frontend domain
cd frontend
railway domain
```

---

## Troubleshooting

### Build Failures

**Check build logs:**
```bash
cd <service>
railway logs --build
```

**Common issues:**
- Missing environment variables
- Dependency conflicts
- Out of memory during build

### Runtime Failures

**Check deployment logs:**
```bash
cd <service>
railway logs --deployment
```

**Common issues:**
- Database connection errors (check PostgreSQL service)
- Redis connection errors (check Redis service)
- Missing environment variables
- Port binding issues (Railway sets $PORT)

### Healthcheck Failures

API healthcheck path: `/api/v1/health`
Trading healthcheck path: `/health`

If healthcheck fails:
1. Check service is listening on $PORT
2. Verify healthcheck path exists
3. Check logs for startup errors

---

## Scaling

Railway auto-scales based on usage. To manually scale:

```bash
cd <service>
railway service scale
```

---

## Rollback

If deployment fails:

```bash
# Redeploy previous version
cd <service>
railway down

# Or use dashboard to rollback
railway open
```

---

## Monitoring Dashboard

Open Railway dashboard:
```bash
railway open
```

Or visit: https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066

---

## Next Steps

1. **Add Database Services:**
   ```bash
   railway add --service postgres
   railway add --service redis
   ```

2. **Set Environment Variables:**
   ```bash
   cd api
   railway variables
   # Set all required variables listed above
   ```

3. **Run Migrations:**
   ```bash
   cd api
   railway run php artisan migrate --force
   ```

4. **Test Deployment:**
   - Visit API health endpoint
   - Test memory creation
   - Verify event bus
   - Check logs for errors

5. **Configure Domains:**
   - Set up custom domains
   - Configure DNS
   - Enable SSL

6. **Monitor:**
   - Watch logs for errors
   - Check resource usage
   - Set up alerts
