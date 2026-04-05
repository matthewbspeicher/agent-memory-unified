# 🚀 Production Deployment Checklist

**Date**: April 5, 2026
**Deploy**: Security Hardening + Hybrid JWT Auth
**Commits**: 9 commits pushed to main
**Status**: Code deployed, migrations pending

---

## ✅ Phase 1: Code Deployment (COMPLETE)

### What Was Pushed
```bash
✅ e381752 deps: add JWT libraries and config
✅ 62a8967 feat: add PHP JWT validator with Redis blacklist
✅ 26e620e feat: add Python JWT validator with hybrid fallback
✅ 601d709 feat: add JWT issuance endpoints
✅ c5bbf84 feat(auth): implement hybrid JWT/legacy authentication for Python
✅ 87e3e6d feat(auth): implement token revocation on agent deactivation
✅ b161190 feat(auth): add Python event consumer framework
✅ 1aa3cb3 security: drop plaintext token columns migration (S1.3)
✅ 123c065 docs: complete security hardening documentation
```

### Auto-Deploy Status
- **GitHub**: ✅ Pushed to matthewbspeicher/agent-memory-unified
- **Railway**: 🔄 Auto-deploying from main branch
- **URL**: https://remembr.dev

### Verify Code Deploy
```bash
# Check Railway deployment status
open https://railway.app/project/your-project/deployments

# Test API is responding
curl https://remembr.dev/api/v1/stats
```

---

## ⏳ Phase 2: Pre-Migration Validation (DO THIS NOW)

### Critical Checks Before Running Migration

#### 1. Environment Variables
```bash
# SSH into Railway or use Railway CLI
railway variables

# Verify these are set:
JWT_SECRET=<256-bit-secret>      # CRITICAL - must be set!
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=15
REDIS_HOST=<redis-host>
REDIS_PORT=6379
DB_CONNECTION=pgsql
```

**🚨 CRITICAL**: If `JWT_SECRET` is not set, JWT authentication will fail!

#### 2. Test Existing Auth (Legacy Tokens)
```bash
# Use an existing agent token
curl https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer amc_YOUR_EXISTING_TOKEN"

# Should return 200 OK with agent profile
```

#### 3. Test JWT Issuance
```bash
# Get a JWT token
curl -X POST https://remembr.dev/api/v1/auth/jwt \
  -H "Authorization: Bearer amc_YOUR_TOKEN"

# Should return:
# {
#   "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
#   "token_type": "Bearer",
#   "expires_in": 900
# }
```

#### 4. Test JWT Auth
```bash
# Use the JWT from step 3
curl https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer <JWT_TOKEN>"

# Should return 200 OK with agent profile
```

#### 5. Check Logs for Errors
```bash
railway logs --tail 100

# Look for:
# - JWT validation errors
# - Redis connection errors
# - Authentication failures
```

---

## ⚠️ Phase 3: Database Migration (WAIT 24 HOURS)

**⏰ DO NOT RUN YET** - Let code soak for 24 hours first!

### Why Wait?
- Verify no JWT authentication errors
- Confirm Redis blacklist is working
- Monitor legacy token usage
- Catch any edge cases in production

### When Ready (After 24 Hours)

#### 1. Backup Database
```bash
# Connect to Supabase
# Go to Database > Backups
# Create manual backup: "pre-migration-security-hardening"

# Or via CLI:
pg_dump -h <supabase-host> -U postgres -d agent_memory > backup-$(date +%Y%m%d).sql
```

#### 2. Schedule Maintenance Window
- **Duration**: 5-10 minutes
- **Time**: Low traffic period (early morning UTC)
- **Notice**: Tweet @RemembrDev about brief maintenance

#### 3. Run Migration
```bash
# SSH to Railway or use CLI
railway run php artisan migrate

# Should see:
# Migrating: 2026_04_05_200325_drop_plaintext_token_columns
# Migrated:  2026_04_05_200325_drop_plaintext_token_columns (0.2 seconds)
```

#### 4. Verify Migration
```bash
railway run php artisan tinker

# Check columns are dropped:
>>> Schema::hasColumn('agents', 'api_token')
=> false  ✅

>>> Schema::hasColumn('agents', 'token_hash')
=> true  ✅

>>> Agent::first()->token_hash
=> "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"  ✅

>>> Agent::first()->api_token
=> null  ✅
```

#### 5. Test Auth Immediately After
```bash
# Test legacy token (should still work)
curl https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer amc_TOKEN"

# Test JWT (should still work)
curl https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer JWT_TOKEN"

# Test deactivated agent (should reject)
# ... (if you have a test deactivated agent)
```

---

## 📊 Phase 4: Post-Deploy Monitoring (24-48 Hours)

### Metrics to Watch

#### Railway Dashboard
- **CPU Usage**: Should be normal (~10-30%)
- **Memory**: Should be stable
- **Response Time**: Should be <200ms p95
- **Error Rate**: Should be <0.1%

#### Custom Metrics (Add to Dashboard)
```bash
# JWT issuance rate
SELECT COUNT(*) FROM agents WHERE created_at > NOW() - INTERVAL '1 hour';

# Legacy token usage (should decline over time)
# Monitor via logs: "Legacy token validated"

# Auth failures
# Monitor via logs: "Authentication failed" or 401 responses

# Revoked token checks
# Monitor Redis: SCARD revoked_tokens:*
```

#### Supabase Logs
```sql
-- Failed auth attempts (check for patterns)
SELECT * FROM logs
WHERE message LIKE '%Authentication failed%'
AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;

-- JWT decode errors
SELECT * FROM logs
WHERE message LIKE '%JWT%error%'
AND created_at > NOW() - INTERVAL '1 hour';
```

#### Redis Health
```bash
railway run redis-cli

# Check blacklist usage
KEYS revoked_tokens:*
SCARD revoked_tokens:<agent_id>

# Check cache hit rate
INFO stats
# Look for: keyspace_hits vs keyspace_misses
```

---

## 🚨 Rollback Procedures

### If JWT Auth Fails (Before Migration)

**Problem**: JWT authentication not working
**Fix**: Debug JWT_SECRET or validator code

```bash
# Check JWT_SECRET is set
railway variables | grep JWT_SECRET

# Check logs for JWT errors
railway logs | grep JWT

# Verify Redis is accessible
railway run redis-cli ping
```

**Rollback**: Just redeploy previous commit (code-only, no migration run)

```bash
git revert HEAD~9..HEAD
git push origin main
# Railway auto-deploys
```

### If Migration Causes Issues (After Migration)

**⚠️ WARNING**: Rollback will LOSE ALL TOKENS. Agents must re-register.

```bash
# Rollback migration (recreates columns, data lost)
railway run php artisan migrate:rollback

# Restore database from backup
pg_restore -h <supabase-host> -U postgres -d agent_memory backup.sql

# Revert code
git revert HEAD~9..HEAD
git push origin main
```

**Post-Rollback**:
1. All agents must re-register (tokens lost)
2. Tweet @RemembrDev about incident
3. Notify agent owners via email
4. Investigate root cause before retry

---

## ✅ Success Criteria

### Code Deploy Success
- [ ] Railway deployment shows "Active"
- [ ] API responds to health checks
- [ ] No spike in error rates
- [ ] Legacy auth still works
- [ ] JWT issuance works
- [ ] JWT authentication works

### Migration Success
- [ ] Migration completes without errors
- [ ] Columns are dropped (verified via tinker)
- [ ] Auth still works (JWT and legacy)
- [ ] No spike in 401 errors
- [ ] Redis blacklist working
- [ ] Agent deactivation working

### 24-Hour Success
- [ ] No authentication outages
- [ ] Auth latency normal (<200ms p95)
- [ ] JWT adoption increasing
- [ ] Legacy token usage declining
- [ ] No unexpected errors in logs

---

## 📞 Contacts

**On-Call**: You (deploying this)
**Escalation**: Check GitHub issues
**Status Page**: Tweet @RemembrDev
**Monitoring**: Railway dashboard + Supabase logs

---

## 📝 Timeline

| Time | Phase | Status |
|------|-------|--------|
| T+0 | Code push to GitHub | ✅ DONE |
| T+2min | Railway auto-deploy | 🔄 In Progress |
| T+5min | Verify code deploy | ⏳ Pending |
| T+10min | Test JWT issuance | ⏳ Pending |
| T+15min | Test JWT auth | ⏳ Pending |
| T+24hr | Decision: run migration? | ⏳ Pending |
| T+24hr+5min | Run migration | ⏳ Pending |
| T+24hr+10min | Verify migration | ⏳ Pending |
| T+48hr | Monitor and celebrate | ⏳ Pending |

---

## 🎯 Next Steps (RIGHT NOW)

1. **Check Railway deployment status**
   ```bash
   open https://railway.app/project/your-project
   ```

2. **Verify JWT_SECRET is set**
   ```bash
   railway variables | grep JWT_SECRET
   ```

3. **Test existing auth (legacy tokens)**
   ```bash
   curl https://remembr.dev/api/v1/agents/me \
     -H "Authorization: Bearer amc_YOUR_TOKEN"
   ```

4. **Test JWT issuance**
   ```bash
   curl -X POST https://remembr.dev/api/v1/auth/jwt \
     -H "Authorization: Bearer amc_YOUR_TOKEN"
   ```

5. **Monitor logs for 24 hours**
   ```bash
   railway logs --tail 100 --follow
   ```

6. **Come back in 24 hours to run migration** ⏰

---

**Deploy Started**: April 5, 2026
**Expected Completion**: April 6, 2026 (after 24hr soak)
**Status**: 🟡 Code Deployed, Migration Pending

🚀 **Good luck!**
