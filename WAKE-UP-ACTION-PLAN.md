# Wake-Up Action Plan

**Status:** Trading service deployed ✅, API/Frontend builds appear stuck

---

## ⚡ Quick Status Check (30 seconds)

```bash
cd /opt/homebrew/var/www/agent-memory-unified
railway deployment list | head -20
```

**Look for:**
- If 7513b752 and 3f03d81f are still BUILDING → they're stuck, proceed to fix
- If they show SUCCESS → great! Skip to "All Services Working" section
- If they show FAILED → check logs and redeploy

---

## 🔧 If Builds Are Stuck (3 minutes)

### Step 1: Cancel Stuck Builds
Visit: https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066

Click each BUILDING deployment → Cancel Build

### Step 2: Verify Service Configuration
For each service (api, trading, frontend), check:
- ✅ Builder: DOCKERFILE (NOT nixpacks)
- ✅ API Root Directory: `api`
- ✅ API Dockerfile Path: `Dockerfile` (relative to api/)
- ✅ Trading Root Directory: (empty/default)
- ✅ Trading Dockerfile Path: `Dockerfile.trading`
- ✅ Frontend Root Directory: (empty/default)
- ✅ Frontend Dockerfile Path: `Dockerfile.frontend`

If ANY service shows wrong config, update it in dashboard.

### Step 3: Trigger Fresh Deployments
```bash
railway up --service api --detach
railway up --service frontend --detach
# Trading already works, but if you want to redeploy:
# railway up --service trading --detach
```

### Step 4: Monitor Build Progress
```bash
# Check status every 2-3 minutes
watch -n 120 "railway deployment list | head -20"
```

Expected times:
- Frontend: 3-5 minutes
- API: 5-10 minutes
- Trading: 15-20 minutes

---

## 🎉 If All Services Are SUCCESS

### Step 1: Get Service URLs
```bash
# In Railway dashboard, each service shows its URL
# Or use CLI:
railway status
```

### Step 2: Test Health Endpoints
```bash
# Trading (already confirmed working)
curl https://your-trading-url/health

# API
curl https://your-api-url/api/v1/health

# Frontend (open in browser)
open https://your-frontend-url
```

### Step 3: Configure Environment Variables
See `DEPLOYMENT-STATUS.md` for full list, but priority ones:

**API Service:**
```env
APP_KEY=(run: railway run --service api php artisan key:generate --show)
DB_CONNECTION=pgsql
DB_HOST=(from Railway Postgres service)
DB_PORT=5432
DB_DATABASE=(from Railway Postgres service)
DB_USERNAME=(from Railway Postgres service)
DB_PASSWORD=(from Railway Postgres service)
REDIS_HOST=(from Railway Redis service)
REDIS_PORT=6379
REDIS_PASSWORD=(from Railway Redis service)
GEMINI_API_KEY=(your key)
```

**Trading Service:**
```env
DATABASE_URL=(PostgreSQL connection string)
REDIS_URL=(Redis connection string)
JWT_SECRET=(generate a random string)
GEMINI_API_KEY=(your key)
```

**Frontend Service:**
```env
VITE_API_URL=https://your-api-url
```

### Step 4: Add Database Services (if not already present)
- Add PostgreSQL to Railway project
- Add Redis to Railway project (may already exist)

### Step 5: Run Migrations
```bash
railway run --service api php artisan migrate --force
```

### Step 6: Verify Everything Works
- Test API endpoints
- Check trading service is responding
- Load frontend in browser and verify API connection
- Test a full flow: create agent → store memory → retrieve memory

---

## 🚨 If Builds Fail

### Check Build Logs
```bash
railway logs <deployment-id>
```

**Common issues and fixes:**

**"Cannot find Dockerfile"**
- Fix: Verify dockerfile paths in Railway dashboard match actual files

**"Redis extension not found" (API)**
- Fix: api/Dockerfile should have pecl install redis (already added)

**"gcc: command not found" (Trading)**
- Fix: Dockerfile.trading should have gcc g++ python3-dev (already added)

**"Module 'app' not found" (Trading)**
- Fix: Should use main:app not api.app:app (already fixed)

**"nixpacks detected"**
- Fix: Builder must be DOCKERFILE in Railway dashboard, not auto-detect

---

## 📋 Verification Checklist

After everything is deployed:

- [ ] Trading service: SUCCESS and responding
- [ ] API service: SUCCESS and responding
- [ ] Frontend service: SUCCESS and loading
- [ ] All services using DOCKERFILE builder (not nixpacks)
- [ ] All services in us-east-1 region
- [ ] Environment variables configured
- [ ] PostgreSQL and Redis added to project
- [ ] Laravel migrations run
- [ ] Health endpoints responding
- [ ] Frontend can connect to API

---

## 🆘 If Nothing Works

**Before panicking:**
1. Trading service already works (76d97b13) - this proves the approach is correct
2. All code is committed and correct in git
3. The issue is likely Railway configuration, not code

**Debug steps:**
1. Compare working trading config with broken API/frontend config
2. Check Railway dashboard service settings vs railway.json
3. Try deploying one service at a time
4. Check Railway status page for platform issues

**Nuclear option (only if desperate):**
1. Delete API and frontend services from Railway
2. Re-create them from scratch using dashboard
3. Manually set: Builder=DOCKERFILE, Dockerfile Path, Root Directory
4. Trigger deployment

---

## 💬 Quick Reference Commands

```bash
# Status check
railway deployment list
railway status

# View logs
railway logs --service api
railway logs --service trading
railway logs --service frontend
railway logs <deployment-id>

# Deploy
railway up --service <name> --detach

# Cancel
railway deployment cancel <deployment-id>

# Run commands in service
railway run --service api php artisan migrate --force
railway run --service api php artisan key:generate --show
```

---

## ✅ Summary

**What's working:** Trading service deployed and running correctly with Dockerfile

**What's unknown:** API/Frontend build status (were stuck, might have completed)

**What to do:** Check status, cancel if stuck, redeploy with confidence knowing the code is correct

**Confidence:** HIGH - Trading proves the approach works. Just need Railway to cooperate.
