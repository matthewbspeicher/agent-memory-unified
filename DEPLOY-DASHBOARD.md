# Railway Dashboard Deployment Guide

**Problem:** CLI deployments keep going to wrong service and wrong region.

**Solution:** Use Railway Dashboard to configure services properly with us-east-1 region.

---

## Step 1: Clean Up Current State

1. Open: https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066
2. Navigate to "postgres" service → Delete it (it's empty and in wrong region)
3. Navigate to "remembr-dev" service → Stop all deployments

---

## Step 2: Configure remembr-dev Service

**Option A: Use remembr-dev as API-only service (Simplest)**

1. Go to remembr-dev service → Settings
2. Set:
   - **Source:** GitHub `matthewbspeicher/remembr-dev`
   - **Root Directory:** `/api`
   - **Build Command:** `composer install --no-dev --optimize-autoloader && php artisan config:cache`
   - **Start Command:** `php artisan octane:start --server=frankenphp --host=0.0.0.0 --port=$PORT`
   - **Region:** Select "us-east-1" (US East)
   - **Healthcheck Path:** `/api/v1/health`
   - **Healthcheck Timeout:** 100
3. Click "Deploy"

---

**Option B: Create 3 Separate Services (Proper Multi-Service)**

### 1. Create API Service

1. Click "+ New Service"
2. Select GitHub repo: `matthewbspeicher/remembr-dev`
3. Service name: `api`
4. Settings:
   - Root Directory: `/api`
   - Build Command: `composer install --no-dev --optimize-autoloader && php artisan config:cache`
   - Start Command: `php artisan octane:start --server=frankenphp --host=0.0.0.0 --port=$PORT`
   - Region: **us-east-1**
   - Healthcheck Path: `/api/v1/health`
   - Healthcheck Timeout: 100

### 2. Create Trading Service

1. Click "+ New Service"
2. Select GitHub repo: `matthewbspeicher/remembr-dev`
3. Service name: `trading`
4. Settings:
   - Root Directory: `/trading`
   - Build Command: `pip install -e .`
   - Start Command: `python3 -m uvicorn api.app:app --host 0.0.0.0 --port $PORT`
   - Region: **us-east-1**
   - Healthcheck Path: `/health`
   - Healthcheck Timeout: 100

### 3. Create Frontend Service

1. Click "+ New Service"
2. Select GitHub repo: `matthewbspeicher/remembr-dev`
3. Service name: `frontend`
4. Settings:
   - Root Directory: `/frontend`
   - Build Command: `npm install && npm run build`
   - Start Command: `npx serve -s dist -l $PORT`
   - Region: **us-east-1**

---

## Step 3: Add Database Services

### PostgreSQL

1. Click "+ New" → "Database" → "PostgreSQL"
2. Name: `postgres`
3. Region: **us-east-1**
4. Let Railway provision automatically

### Redis (Already exists)

- ✅ Redis service already running
- Check region: Should be us-east, if not, create new Redis in us-east-1

---

## Step 4: Configure Environment Variables

### For API Service

Go to service → Variables tab → Add these:

```env
APP_ENV=production
APP_DEBUG=false
APP_KEY=                 # Generate: php artisan key:generate --show

DB_CONNECTION=pgsql
DB_HOST=${{Postgres.PGHOST}}
DB_PORT=${{Postgres.PGPORT}}
DB_DATABASE=${{Postgres.PGDATABASE}}
DB_USERNAME=${{Postgres.PGUSER}}
DB_PASSWORD=${{Postgres.PGPASSWORD}}

REDIS_HOST=${{Redis.REDIS_HOST}}
REDIS_PORT=${{Redis.REDIS_PORT}}
REDIS_PASSWORD=${{Redis.REDIS_PASSWORD}}

GEMINI_API_KEY=          # Your Gemini key
```

### For Trading Service

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=redis://default:${{Redis.REDIS_PASSWORD}}@${{Redis.REDIS_HOST}}:${{Redis.REDIS_PORT}}

LOG_LEVEL=INFO
JWT_SECRET=              # Generate: openssl rand -base64 32
```

### For Frontend Service

```env
VITE_API_URL=https://your-api-domain.railway.app
```

---

## Step 5: Run Migrations

After API service deploys successfully:

1. Go to API service → Deployments tab
2. Click on successful deployment
3. Open "Console" or "Shell"
4. Run: `php artisan migrate --force`

**OR via Railway CLI:**

```bash
cd /opt/homebrew/var/www/agent-memory-unified
railway link --project hopeful-presence --service api
railway run php artisan migrate --force
```

---

## Step 6: Verify Deployments

### API Health Check

```bash
curl https://your-api-domain.railway.app/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "...",
  "database": "connected",
  "redis": "connected"
}
```

### Trading Health Check

```bash
curl https://your-trading-domain.railway.app/health
```

Expected response:
```json
{
  "status": "healthy"
}
```

### Frontend

Open in browser: `https://your-frontend-domain.railway.app`

---

## Step 7: Configure Custom Domains (Optional)

### For API Service

1. Go to API service → Settings → Domains
2. Click "Add Domain"
3. Enter: `api.remembr.dev` (or your domain)
4. Configure DNS:
   ```
   CNAME api.remembr.dev → <railway-provided-cname>
   ```

### For Frontend

1. Go to Frontend service → Settings → Domains
2. Use existing: `remembr.dev` (already configured)
3. OR add new subdomain

---

## Troubleshooting

### Build Fails

- Check build logs in Railway dashboard
- Common issues:
  - Missing nixpacks.toml (already created in each directory)
  - Wrong start command (check railway.json in each directory)
  - Missing dependencies (check composer.json / package.json / pyproject.toml)

### Healthcheck Fails

- Verify healthcheck paths exist:
  - API: `/api/v1/health`
  - Trading: `/health`
- Check logs for startup errors
- Verify port binding (`$PORT` environment variable)

### Database Connection Errors

- Ensure PostgreSQL service is running
- Check environment variables are set correctly
- Verify database references: `${{Postgres.PGHOST}}` format
- Run migrations: `railway run php artisan migrate --force`

### Redis Connection Errors

- Check Redis service is running
- Verify Redis password is set correctly
- Test connection in API logs

---

## Expected Timeline

- **Option A (API-only):** 10 minutes
  - 5 min: Configure service
  - 5 min: Build and deploy

- **Option B (3 services):** 20-30 minutes
  - 10 min: Create and configure services
  - 10 min: Build and deploy all 3
  - 5 min: Configure environment variables
  - 5 min: Run migrations and verify

---

## Files Ready

All configuration files are committed and ready:

```
✅ railway.json (root) - Multi-service config
✅ api/railway.json - Laravel config
✅ api/nixpacks.toml - PHP 8.3 build
✅ trading/railway.json - Python config
✅ trading/nixpacks.toml - Python 3.14 build
✅ frontend/railway.json - React config
✅ All services configured for us-east-1 region
```

Railway will automatically detect these configs when building from the specified root directories.

---

## Next Steps

**Choose your approach:**

1. **Fast track:** Option A (API-only) → 10 minutes to running API
2. **Proper setup:** Option B (3 services) → 30 minutes to full stack

Once services are deployed and verified, you can:
- Test API endpoints
- Create agents and memories
- View public feed at dashboard.html
- Monitor deployments in Railway dashboard

---

## Need Help?

If you get stuck:
1. Check Railway dashboard logs
2. Run `./verify_deployment.sh` locally
3. Check `RAILWAY-STATUS.md` for current state
4. Ask for specific help with the error message
