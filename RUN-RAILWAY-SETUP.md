# Run Railway Multi-Service Setup Script

This script uses Railway's GraphQL API to create 3 services properly configured in us-east-1.

---

## Step 1: Get Your Railway API Token (2 minutes)

1. Go to: https://railway.app/account/tokens
2. Click "Create New Token"
3. Name it: `CLI Deployment`
4. Copy the token (starts with `railway_...`)

---

## Step 2: Export the Token

```bash
export RAILWAY_API_TOKEN='railway_your_token_here'
```

**Verify it's set:**
```bash
echo $RAILWAY_API_TOKEN
```

---

## Step 3: Install Dependencies

```bash
pip3 install requests
```

Or if you prefer virtual environment:
```bash
cd /opt/homebrew/var/www/agent-memory-unified
python3 -m venv venv
source venv/bin/activate
pip install requests
```

---

## Step 4: Run the Setup Script

```bash
cd /opt/homebrew/var/www/agent-memory-unified
python3 setup-railway-services.py
```

Expected output:
```
🚂 Railway Multi-Service Setup
============================================================
Project ID: 21c3f323-784d-4ec4-8828-1bc190723066
Environment: 1dfff0f0-d45a-4b73-91d7-adba7bbd46ed
GitHub Repo: matthewbspeicher/remembr-dev
Target Region: us-east-1
============================================================

============================================================
🔧 Setting up API Service
============================================================
📦 Creating service: api
✅ Created service: api (ID: ...)
⚙️  Configuring service settings...
✅ Service configured: root=/api, start=php artisan octane:start...
ℹ️  Region configuration: us-east-1 (set via environment or project settings)

============================================================
🐍 Setting up Trading Service
============================================================
📦 Creating service: trading
✅ Created service: trading (ID: ...)
⚙️  Configuring service settings...
✅ Service configured: root=/trading, start=python3 -m uvicorn...
ℹ️  Region configuration: us-east-1 (set via environment or project settings)

============================================================
⚛️  Setting up Frontend Service
============================================================
📦 Creating service: frontend
✅ Created service: frontend (ID: ...)
⚙️  Configuring service settings...
✅ Service configured: root=/frontend, start=npx serve...
ℹ️  Region configuration: us-east-1 (set via environment or project settings)

============================================================
🚀 Triggering Deployments
============================================================

📦 Deploying API service...
✅ Deployment started

📦 Deploying Trading service...
✅ Deployment started

📦 Deploying Frontend service...
✅ Deployment started

============================================================
✅ Setup Complete!
============================================================

Services created:
  - api:      abc123...
  - trading:  def456...
  - frontend: ghi789...

📊 Monitor deployments:
  https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066

⏳ Next steps:
  1. Wait for builds to complete (5-10 minutes)
  2. Add PostgreSQL: railway add --database postgres
  3. Configure environment variables
  4. Run migrations: railway run php artisan migrate --force

💡 Tip: Check DEPLOY-STEPS.md for environment variable setup
```

---

## Step 5: Monitor Deployments

Open Railway dashboard:
```bash
railway open
```

Or visit: https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066

You should see 3 services building:
- ✅ **api** - Building in us-east-1
- ✅ **trading** - Building in us-east-1
- ✅ **frontend** - Building in us-east-1

---

## Step 6: Add Database Services

Once services are created, add PostgreSQL:

```bash
cd /opt/homebrew/var/www/agent-memory-unified
railway add --database postgres
```

When prompted:
- Region: **us-east-1**

Redis already exists in the project, but check its region:
```bash
railway service status
```

If Redis is not in us-east-1, create a new one:
```bash
railway add --database redis
```

---

## Step 7: Configure Environment Variables

See **DEPLOY-STEPS.md** Step 6 for complete environment variable setup.

**Quick reference:**

### API Service
```bash
# Generate APP_KEY locally first
cd api
php artisan key:generate --show
# Copy the output

# Then set via Railway dashboard or CLI:
railway variables
```

Required variables:
```env
APP_ENV=production
APP_DEBUG=false
APP_KEY=base64:... (from above)
DB_CONNECTION=pgsql
DB_HOST=${{Postgres.PGHOST}}
DB_PORT=${{Postgres.PGPORT}}
DB_DATABASE=${{Postgres.PGDATABASE}}
DB_USERNAME=${{Postgres.PGUSER}}
DB_PASSWORD=${{Postgres.PGPASSWORD}}
REDIS_HOST=${{Redis.REDIS_HOST}}
REDIS_PORT=${{Redis.REDIS_PORT}}
REDIS_PASSWORD=${{Redis.REDIS_PASSWORD}}
GEMINI_API_KEY=your-key
```

### Trading Service
```bash
openssl rand -base64 32  # Generate JWT_SECRET
```

Required variables:
```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=redis://default:${{Redis.REDIS_PASSWORD}}@${{Redis.REDIS_HOST}}:${{Redis.REDIS_PORT}}
LOG_LEVEL=INFO
JWT_SECRET=... (from above)
```

### Frontend Service
```env
VITE_API_URL=${{api.RAILWAY_PUBLIC_DOMAIN}}
```

---

## Step 8: Run Migrations

After API service deploys and environment variables are set:

```bash
cd /opt/homebrew/var/www/agent-memory-unified
railway link --service api
railway run php artisan migrate --force
```

Expected output:
```
Migrating: 2024_01_01_000000_create_agents_table
Migrated:  2024_01_01_000000_create_agents_table (123ms)
Migrating: 2024_01_01_000001_create_memories_table
Migrated:  2024_01_01_000001_create_memories_table (234ms)
...
(83 migrations total)
```

---

## Step 9: Verify Deployments

### Check API Health
```bash
curl https://api-production-abc123.up.railway.app/api/v1/health
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

### Check Trading Health
```bash
curl https://trading-production-def456.up.railway.app/health
```

Expected:
```json
{
  "status": "healthy"
}
```

### Check Frontend
Open in browser: `https://frontend-production-ghi789.up.railway.app`

Should see the login page.

---

## Troubleshooting

### Script Fails with "401 Unauthorized"

**Problem:** Invalid or expired API token

**Fix:**
1. Go to https://railway.app/account/tokens
2. Create a new token
3. Export it: `export RAILWAY_API_TOKEN='new-token'`
4. Run script again

---

### Services Created but Wrong Region

**Problem:** Railway API might not support region setting via GraphQL

**Fix:**
1. Go to Railway dashboard
2. For each service → Settings → Region
3. Change to **us-east-1**
4. Redeploy

---

### "Service not found" when linking

**Problem:** Railway CLI cache issue

**Fix:**
```bash
rm -rf ~/.railway
railway login
cd /opt/homebrew/var/www/agent-memory-unified
railway link 21c3f323-784d-4ec4-8828-1bc190723066
# Select the service when prompted
```

---

### Build Fails

**Check build logs:**
```bash
cd /opt/homebrew/var/www/agent-memory-unified
railway logs --build
```

**Common issues:**
- Wrong start command → Check railway.json and nixpacks.toml in each directory
- Missing dependencies → Check composer.json / package.json / pyproject.toml
- Wrong root directory → Verify in Railway dashboard: Settings → Root Directory

---

## What the Script Does

1. **Creates 3 services** via Railway GraphQL API:
   - `api` (Laravel PHP 8.3)
   - `trading` (Python 3.14 FastAPI)
   - `frontend` (React + Vite)

2. **Configures each service:**
   - Root directory (subdirectory in monorepo)
   - Start command (from railway.json/nixpacks.toml)
   - Healthcheck path (API and Trading only)
   - GitHub repo connection

3. **Triggers initial deployments:**
   - Builds from respective root directories
   - Uses Nixpacks builder (auto-detected)
   - Respects railway.json and nixpacks.toml configs

4. **Outputs service IDs:**
   - For environment variable configuration
   - For linking via CLI
   - For monitoring deployments

---

## After Setup

Once all services are deployed and verified:

1. **Configure custom domains** (optional)
2. **Set up monitoring/alerts**
3. **Test the full stack:**
   - Create a user account
   - Register an agent
   - Create memories
   - View public feed
4. **Monitor resource usage**
5. **Scale if needed**

---

## Files Created

The script uses existing configuration files:
- ✅ `api/railway.json` - Laravel config
- ✅ `api/nixpacks.toml` - PHP build config
- ✅ `trading/railway.json` - Python config
- ✅ `trading/nixpacks.toml` - Python build config
- ✅ `frontend/railway.json` - React config

All with **us-east-1** region specified in railway.json.

---

## Cost Estimate

**Railway Hobby Plan:**
- 3 services × $5-10/month = $15-30/month
- PostgreSQL: $5-10/month
- Redis: $5/month (already running)
- **Total: ~$25-45/month**

**Free tier credit:** $5/month, so first month might be ~$20-40

---

## Next Steps

After successful deployment:

1. **Test API endpoints**
2. **Create first agent**
3. **Test memory creation**
4. **Verify event bus** (Laravel → Python communication)
5. **Monitor logs** for errors
6. **Set up custom domains**
7. **Configure alerts**

See **DEPLOY-STEPS.md** for detailed post-deployment checklist.
