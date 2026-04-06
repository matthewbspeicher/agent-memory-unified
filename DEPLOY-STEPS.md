# Railway Multi-Service Deployment - Step by Step

**Goal:** Create 3 services (API, Trading, Frontend) all in us-east-1 region

**Time:** ~30 minutes

---

## Step 1: Clean Up (2 minutes)

1. Open: https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066
2. Find "postgres" service (the empty one that failed)
   - Click on it
   - Settings → Scroll down → "Delete Service"
3. Find "remembr-dev" service
   - Click on latest deployment
   - Click "Stop Deployment" or "Cancel Build"
   - Do NOT delete this service yet (we'll reconfigure it)

---

## Step 2: Reconfigure "remembr-dev" as API Service (5 minutes)

1. Click on "remembr-dev" service
2. Go to **Settings** tab
3. **Service Settings:**
   - Change name to: `api` (optional but clearer)
   - Leave source as: GitHub `matthewbspeicher/remembr-dev`
4. **Root Directory:**
   - Click "Configure"
   - Set to: `api`
   - Save
5. **Build Settings:**
   - Build Command: (leave empty - nixpacks.toml handles it)
   - Builder: NIXPACKS (should be default)
6. **Deploy Settings:**
   - Start Command: (leave empty - nixpacks.toml handles it)
   - Region: **Change to us-east-1**
7. **Healthcheck:**
   - Path: `/api/v1/health`
   - Timeout: 100
8. Click "Deploy" at the top

**Monitor:** Watch the build logs - should take 3-5 minutes

---

## Step 3: Create Trading Service (5 minutes)

1. Click "+ New" (top right) → "Empty Service"
2. **Service name:** `trading`
3. **Source:**
   - Click "Connect Repo"
   - Select: `matthewbspeicher/remembr-dev`
   - Connect
4. **Settings:**
   - Root Directory: `trading`
   - Region: **us-east-1**
   - Builder: NIXPACKS
5. **Healthcheck:**
   - Path: `/health`
   - Timeout: 100
6. Save and Deploy

**Monitor:** Watch build logs

---

## Step 4: Create Frontend Service (5 minutes)

1. Click "+ New" → "Empty Service"
2. **Service name:** `frontend`
3. **Source:**
   - Connect to same repo: `matthewbspeicher/remembr-dev`
4. **Settings:**
   - Root Directory: `frontend`
   - Region: **us-east-1**
   - Builder: NIXPACKS
5. Save and Deploy

**Monitor:** Watch build logs

---

## Step 5: Add PostgreSQL Database (2 minutes)

1. Click "+ New" → "Database" → "Add PostgreSQL"
2. **Name:** `postgres`
3. **Region:** **us-east-1** (IMPORTANT)
4. Let Railway provision it
5. Wait for it to show "Running" status

---

## Step 6: Configure Environment Variables (10 minutes)

### For API Service

1. Go to `api` service → **Variables** tab
2. Click "Add Variable" for each:

```env
APP_ENV=production
APP_DEBUG=false
APP_KEY=base64:GENERATE_THIS_LOCALLY

DB_CONNECTION=pgsql
DB_HOST=${{Postgres.PGHOST}}
DB_PORT=${{Postgres.PGPORT}}
DB_DATABASE=${{Postgres.PGDATABASE}}
DB_USERNAME=${{Postgres.PGUSER}}
DB_PASSWORD=${{Postgres.PGPASSWORD}}

REDIS_HOST=${{Redis.REDIS_HOST}}
REDIS_PORT=${{Redis.REDIS_PORT}}
REDIS_PASSWORD=${{Redis.REDIS_PASSWORD}}

GEMINI_API_KEY=YOUR_GEMINI_KEY_HERE
```

**To generate APP_KEY locally:**
```bash
cd /opt/homebrew/var/www/agent-memory-unified/api
php artisan key:generate --show
# Copy the output and paste it as APP_KEY value
```

### For Trading Service

1. Go to `trading` service → **Variables** tab
2. Add these:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=redis://default:${{Redis.REDIS_PASSWORD}}@${{Redis.REDIS_HOST}}:${{Redis.REDIS_PORT}}

LOG_LEVEL=INFO
JWT_SECRET=GENERATE_THIS_LOCALLY
```

**To generate JWT_SECRET locally:**
```bash
openssl rand -base64 32
# Copy the output and paste it as JWT_SECRET value
```

### For Frontend Service

1. Go to `frontend` service → **Variables** tab
2. Add this:

```env
VITE_API_URL=${{api.RAILWAY_PUBLIC_DOMAIN}}
```

Or if you want to use a custom domain:
```env
VITE_API_URL=https://api.remembr.dev
```

---

## Step 7: Wait for All Services to Build (5-10 minutes)

Watch the deployments page. You should see:
- ✅ `api` - Building → Running
- ✅ `trading` - Building → Running
- ✅ `frontend` - Building → Running
- ✅ `postgres` - Running
- ✅ `Redis` - Running (already was)

---

## Step 8: Run Database Migrations (2 minutes)

Once API service shows "Running":

**Option A: Via Dashboard Console**
1. Go to `api` service
2. Click on the green deployment
3. Click "View Logs" → Find the "Console" or "Shell" tab
4. Run: `php artisan migrate --force`

**Option B: Via Railway CLI (recommended)**
```bash
cd /opt/homebrew/var/www/agent-memory-unified

# Link to the API service
railway link 21c3f323-784d-4ec4-8828-1bc190723066

# Then select the "api" service when prompted

# Run migrations
railway run php artisan migrate --force
```

Expected output:
```
Migrating: ...
Migrated: ...
```

---

## Step 9: Verify Deployments (3 minutes)

### Check API

```bash
# Get the API domain from Railway dashboard
curl https://api-service-production.up.railway.app/api/v1/health
```

Expected:
```json
{
  "status": "healthy",
  "timestamp": "2026-04-05T...",
  "database": "connected",
  "redis": "connected"
}
```

### Check Trading

```bash
curl https://trading-service-production.up.railway.app/health
```

Expected:
```json
{
  "status": "healthy"
}
```

### Check Frontend

Open in browser:
```
https://frontend-service-production.up.railway.app
```

Should see the login page.

---

## Step 10: Configure Custom Domains (Optional)

### API Domain

1. Go to `api` service → **Settings** → **Domains**
2. Click "Add Domain"
3. Enter: `api.remembr.dev`
4. Railway will show you the CNAME record to add to your DNS:
   ```
   CNAME api.remembr.dev → xxx.railway.app
   ```
5. Add that record in your DNS provider (Cloudflare, etc.)
6. Wait for DNS propagation (1-5 minutes)

### Frontend Domain

1. Go to `frontend` service → **Settings** → **Domains**
2. The existing `remembr.dev` domain might need to be moved from the old service
3. If needed, remove it from old service and add to `frontend` service
4. Or add a new subdomain: `app.remembr.dev`

---

## Troubleshooting

### API Build Fails

**Check logs for:**
- Composer errors → Check composer.json
- PHP version mismatch → nixpacks.toml specifies PHP 8.3
- Missing extensions → Check if FrankenPHP includes required extensions

**Common fixes:**
- Ensure `composer.lock` is committed
- Check nixpacks.toml exists in `api/` directory
- Verify `api/railway.json` is present

### Trading Build Fails

**Check logs for:**
- Python package errors → Check pyproject.toml
- Missing dependencies → Check requirements.txt vs pyproject.toml

**Common fixes:**
- Ensure all Python packages are in pyproject.toml
- Check nixpacks.toml specifies Python 3.14
- Verify trading/railway.json exists

### Frontend Build Fails

**Check logs for:**
- npm install errors → Check package.json
- Build errors → Check for TypeScript errors locally first

**Common fixes:**
- Run `npm install` locally to verify
- Check that `dist/` is in .gitignore (shouldn't be committed)
- Verify frontend/railway.json exists

### Healthcheck Fails

**API healthcheck failing:**
- Check if `/api/v1/health` endpoint exists
- View logs to see if server started
- Verify port binding: should use `$PORT` environment variable

**Trading healthcheck failing:**
- Check if `/health` endpoint exists in trading/api/app.py
- Verify uvicorn is binding to `0.0.0.0:$PORT`

### Database Connection Errors

**Check:**
1. PostgreSQL service is running (green status in dashboard)
2. Environment variables are set correctly in API service
3. Variable references use `${{Postgres.PGHOST}}` format (not plain text)
4. Database migrations ran successfully

**Fix:**
```bash
# Re-run migrations
railway run php artisan migrate --force

# Or reset and migrate (⚠️ destroys data)
railway run php artisan migrate:fresh --force
```

### Redis Connection Errors

**Check:**
1. Redis service is running
2. Redis PASSWORD variable is set
3. Variable references use `${{Redis.REDIS_PASSWORD}}` format

### Frontend Can't Connect to API

**Check:**
1. VITE_API_URL is set correctly in frontend variables
2. API service has a public domain
3. CORS is configured in API (check api/config/cors.php)

---

## Success Checklist

Once everything is running, you should have:

- ✅ All 5 services in **us-east-1** region:
  - `api` (Laravel API)
  - `trading` (Python FastAPI)
  - `frontend` (React app)
  - `postgres` (Database)
  - `Redis` (Cache)

- ✅ All health checks passing:
  - API: `/api/v1/health` returns 200
  - Trading: `/health` returns 200

- ✅ Database migrations completed:
  - 83 tables created
  - No migration errors

- ✅ Frontend loads:
  - Login page visible
  - Can create account
  - Can log in

---

## Next Steps After Deployment

1. **Test the API:**
   ```bash
   # Register a user
   curl -X POST https://api.remembr.dev/api/v1/register \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","name":"Test User"}'

   # Get magic link from email
   # Click link to verify
   ```

2. **Test Agent Registration:**
   ```bash
   # Create an agent
   curl -X POST https://api.remembr.dev/api/v1/agents/register \
     -H "Content-Type: application/json" \
     -d '{"name":"TestBot","owner_token":"YOUR_TOKEN"}'
   ```

3. **Test Memory Creation:**
   ```bash
   curl -X POST https://api.remembr.dev/api/v1/memories \
     -H "Authorization: Bearer YOUR_AGENT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"value":"Test memory","visibility":"public"}'
   ```

4. **Monitor Logs:**
   - API logs: Railway dashboard → api service → Logs
   - Trading logs: Railway dashboard → trading service → Logs
   - Check for errors, warnings, performance issues

5. **Set Up Monitoring:**
   - Enable Railway metrics
   - Set up alerts for service failures
   - Monitor resource usage (CPU, memory, bandwidth)

---

## Estimated Costs

**Railway Pricing (Hobby plan):**
- **5 services running:** ~$5-10/month per service = $25-50/month
- **Database storage:** ~$5-10/month (depends on usage)
- **Bandwidth:** $0.10/GB after free tier

**Total:** ~$30-60/month for low-medium traffic

**Free tier:** $5/month credit, so first month might be free if usage is low.

---

## Files Committed and Ready

All configuration files are already in the repo:

```
✅ api/railway.json
✅ api/nixpacks.toml
✅ trading/railway.json
✅ trading/nixpacks.toml
✅ frontend/railway.json
✅ railway.json (root - multi-service config)
```

Railway will automatically detect and use these when building from the root directories you specify.

---

## Summary

You're setting up a proper production architecture:
- **3 separate services** for proper separation of concerns
- **All in us-east-1** for consistent latency
- **Shared PostgreSQL and Redis** for data layer
- **Health checks** on all services
- **Environment variables** properly configured
- **Database migrations** run automatically

This setup is scalable, maintainable, and follows Railway best practices.

**Ready to start? Open the Railway dashboard and follow Step 1!**
