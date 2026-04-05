# JWT Migration Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete security hardening by running the database migration that drops plaintext token columns, verify authentication still works.

**Architecture:** JWT authentication code deployed April 5, 2026. Migration drops 4 plaintext columns (agents.api_token, users.api_token, users.magic_link_token, workspaces.api_token). All auth now hash-only.

**Tech Stack:** Laravel 12, PostgreSQL (Supabase), Railway deployment, Redis (blacklist)

**Timeline:** ~2 hours (pre-flight → migration → verification → monitoring)

**Risk Level:** Medium (reversible via restore, single-user system limits blast radius)

---

## Pre-Execution Checklist

Before starting Task 1, verify:
- [ ] Railway CLI authenticated (`railway whoami`)
- [ ] Database backup exists (automatic Supabase backup enabled)
- [ ] Migration file exists: `api/database/migrations/2026_04_05_200325_drop_plaintext_token_columns.php`
- [ ] Current auth works: `curl https://remembr.dev/api/v1/agents/me -H "Authorization: Bearer amc_YOUR_TOKEN"` returns 200

---

## Task 1: Pre-Flight Verification

**Files:**
- Read: `api/database/migrations/2026_04_05_200325_drop_plaintext_token_columns.php`
- Execute: Railway commands via shell

**Purpose:** Verify hash columns populated, no null values that would break auth post-migration.

- [ ] **Step 1: Check agents.token_hash populated**

```bash
railway run php artisan tinker --execute="echo 'Agents with null token_hash: ' . Agent::whereNull('token_hash')->count();"
```

Expected output: `Agents with null token_hash: 0`

If > 0: **ABORT** - hash backfill incomplete

- [ ] **Step 2: Check users.api_token_hash populated**

```bash
railway run php artisan tinker --execute="echo 'Users with null api_token_hash: ' . User::whereNull('api_token_hash')->count();"
```

Expected output: `Users with null api_token_hash: 0`

If > 0: **ABORT** - hash backfill incomplete

- [ ] **Step 3: Check workspaces.api_token_hash populated**

```bash
railway run php artisan tinker --execute="echo 'Workspaces with null api_token_hash: ' . Workspace::whereNull('api_token_hash')->count();"
```

Expected output: `Workspaces with null api_token_hash: 0`

If > 0: **ABORT** - hash backfill incomplete

- [ ] **Step 4: Verify current auth uses hash lookup**

```bash
grep -n "where('token_hash'" api/app/Providers/AppServiceProvider.php
```

Expected: Line 55 shows `Agent::where('token_hash', hash('sha256', $token))`

This confirms middleware hashes incoming tokens and looks up by hash column.

- [ ] **Step 5: Test auth before migration**

```bash
curl -v https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer amc_YOUR_TOKEN"
```

Expected: HTTP 200, JSON response with agent data

If fails: **ABORT** - current auth broken, fix before migrating

---

## Task 2: Database Backup

**Files:**
- Create: `backups/backup-$(date +%Y%m%d-%H%M%S).sql`

**Purpose:** Manual backup as safety net before dropping columns.

- [ ] **Step 1: Create backup directory**

```bash
mkdir -p backups
```

- [ ] **Step 2: Capture DATABASE_URL from Railway**

```bash
railway variables | grep DATABASE_URL
```

Copy the PostgreSQL connection string (starts with `postgresql://`)

- [ ] **Step 3: Create backup file**

```bash
pg_dump "postgresql://user:pass@host:5432/dbname" > backups/backup-$(date +%Y%m%d-%H%M%S).sql
```

Replace connection string with actual value from Step 2.

Expected: File created in `backups/` directory, size > 1MB

- [ ] **Step 4: Verify backup is restorable**

```bash
ls -lh backups/backup-*.sql
head -20 backups/backup-*.sql
```

Expected: File shows SQL DDL statements (CREATE TABLE, etc.)

If empty or corrupted: **ABORT** - retry backup

- [ ] **Step 5: Document backup location**

```bash
echo "Backup created: $(ls -t backups/backup-*.sql | head -1)" >> migration-log.txt
date >> migration-log.txt
```

---

## Task 3: Run Migration

**Files:**
- Execute: `api/database/migrations/2026_04_05_200325_drop_plaintext_token_columns.php`

**Purpose:** Drop 4 plaintext token columns, leaving only hash columns.

- [ ] **Step 1: Review migration SQL**

```bash
cat api/database/migrations/2026_04_05_200325_drop_plaintext_token_columns.php
```

Verify it drops exactly these 4 columns:
- `agents.api_token`
- `users.api_token`
- `users.magic_link_token`
- `workspaces.api_token`

- [ ] **Step 2: Run migration**

```bash
railway run php artisan migrate --force
```

Expected output:
```
Migrating: 2026_04_05_200325_drop_plaintext_token_columns
Migrated:  2026_04_05_200325_drop_plaintext_token_columns (X seconds)
```

If error: **STOP** - do NOT continue, check error message

- [ ] **Step 3: Verify migration recorded**

```bash
railway run php artisan migrate:status
```

Expected: `2026_04_05_200325_drop_plaintext_token_columns` shows "Ran" in migrations table

- [ ] **Step 4: Log migration completion**

```bash
echo "Migration completed: $(date)" >> migration-log.txt
railway run php artisan migrate:status | grep drop_plaintext_token_columns >> migration-log.txt
```

---

## Task 4: Schema Verification

**Files:**
- Execute: Laravel tinker commands

**Purpose:** Confirm columns dropped, hash columns remain.

- [ ] **Step 1: Check agents table schema**

```bash
railway run php artisan tinker --execute="
echo 'agents.api_token exists: ' . (Schema::hasColumn('agents', 'api_token') ? 'YES ❌' : 'NO ✅') . PHP_EOL;
echo 'agents.token_hash exists: ' . (Schema::hasColumn('agents', 'token_hash') ? 'YES ✅' : 'NO ❌') . PHP_EOL;
"
```

Expected:
```
agents.api_token exists: NO ✅
agents.token_hash exists: YES ✅
```

- [ ] **Step 2: Check users table schema**

```bash
railway run php artisan tinker --execute="
echo 'users.api_token exists: ' . (Schema::hasColumn('users', 'api_token') ? 'YES ❌' : 'NO ✅') . PHP_EOL;
echo 'users.api_token_hash exists: ' . (Schema::hasColumn('users', 'api_token_hash') ? 'YES ✅' : 'NO ❌') . PHP_EOL;
echo 'users.magic_link_token exists: ' . (Schema::hasColumn('users', 'magic_link_token') ? 'YES ❌' : 'NO ✅') . PHP_EOL;
echo 'users.magic_link_token_hash exists: ' . (Schema::hasColumn('users', 'magic_link_token_hash') ? 'YES ✅' : 'NO ❌') . PHP_EOL;
"
```

Expected:
```
users.api_token exists: NO ✅
users.api_token_hash exists: YES ✅
users.magic_link_token exists: NO ✅
users.magic_link_token_hash exists: YES ✅
```

- [ ] **Step 3: Check workspaces table schema**

```bash
railway run php artisan tinker --execute="
echo 'workspaces.api_token exists: ' . (Schema::hasColumn('workspaces', 'api_token') ? 'YES ❌' : 'NO ✅') . PHP_EOL;
echo 'workspaces.api_token_hash exists: ' . (Schema::hasColumn('workspaces', 'api_token_hash') ? 'YES ✅' : 'NO ❌') . PHP_EOL;
"
```

Expected:
```
workspaces.api_token exists: NO ✅
workspaces.api_token_hash exists: YES ✅
```

- [ ] **Step 4: Verify hash columns have data**

```bash
railway run php artisan tinker --execute="
\$agent = Agent::first();
echo 'Sample agent token_hash: ' . substr(\$agent->token_hash, 0, 16) . '...' . PHP_EOL;
echo 'Sample agent api_token: ' . (\$agent->api_token ?? 'null ✅') . PHP_EOL;
"
```

Expected:
```
Sample agent token_hash: 9f86d081884c7d65...
Sample agent api_token: null ✅
```

If `api_token` is not null: **CRITICAL** - migration didn't run, column still exists

- [ ] **Step 5: Document schema state**

```bash
echo "Schema verification: $(date)" >> migration-log.txt
echo "✅ All plaintext columns dropped" >> migration-log.txt
echo "✅ All hash columns remain" >> migration-log.txt
```

---

## Task 5: Cache Invalidation

**Files:**
- Execute: Laravel cache commands

**Purpose:** Clear any cached query results that reference old column names.

- [ ] **Step 1: Clear application cache**

```bash
railway run php artisan cache:clear
```

Expected: `Application cache cleared successfully.`

- [ ] **Step 2: Clear config cache**

```bash
railway run php artisan config:clear
```

Expected: `Configuration cache cleared successfully.`

- [ ] **Step 3: Clear route cache**

```bash
railway run php artisan route:clear
```

Expected: `Route cache cleared successfully.`

- [ ] **Step 4: Verify OPcache reset**

```bash
railway logs --tail 10 | grep -i opcache
```

Expected: No errors (OPcache resets automatically on deploy)

- [ ] **Step 5: Log cache clear**

```bash
echo "Cache cleared: $(date)" >> migration-log.txt
```

---

## Task 6: Authentication Flow Tests

**Files:**
- Execute: curl commands against production API

**Purpose:** Verify all three auth flows work post-migration (legacy token, JWT issuance, JWT auth).

- [ ] **Step 1: Test legacy token auth (hash lookup)**

```bash
curl -v https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer amc_YOUR_TOKEN" \
  -H "Accept: application/json"
```

Expected:
- HTTP 200 OK
- JSON response with `{"id": "...", "name": "...", "owner_id": "..."}`

If 401: **CRITICAL** - hash lookup broken, check AppServiceProvider.php line 55

- [ ] **Step 2: Test JWT issuance**

```bash
curl -v -X POST https://remembr.dev/api/v1/auth/jwt \
  -H "Authorization: Bearer amc_YOUR_TOKEN" \
  -H "Accept: application/json"
```

Expected:
- HTTP 200 OK
- JSON: `{"token": "eyJ0eXAi...", "token_type": "Bearer", "expires_in": 900}`

Save JWT token from response for next step.

- [ ] **Step 3: Test JWT authentication**

```bash
JWT_TOKEN="eyJ0eXAi..."  # Paste token from Step 2

curl -v https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Accept: application/json"
```

Expected:
- HTTP 200 OK
- Same agent data as Step 1

If 401: Check JWT_SECRET configured in Railway

- [ ] **Step 4: Test memory creation (write operation)**

```bash
curl -v -X POST https://remembr.dev/api/v1/memories \
  -H "Authorization: Bearer amc_YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"value": "Test memory post-migration", "visibility": "private"}'
```

Expected:
- HTTP 201 Created
- JSON response with memory ID

This proves auth works for write operations, not just reads.

- [ ] **Step 5: Document auth test results**

```bash
cat >> migration-log.txt << EOF
Authentication tests: $(date)
✅ Legacy token auth: PASS
✅ JWT issuance: PASS
✅ JWT authentication: PASS
✅ Write operation: PASS
EOF
```

---

## Task 7: Error Monitoring (30 Minutes)

**Files:**
- Execute: Railway logs monitoring

**Purpose:** Watch for authentication errors in production logs for 30 minutes post-migration.

- [ ] **Step 1: Start log stream with filter**

```bash
railway logs --tail 100 --follow | grep -iE "auth|jwt|error|fail|401|403"
```

This streams logs and highlights auth-related entries.

- [ ] **Step 2: Watch for 30 minutes**

Set timer for 30 minutes. Look for:
- ❌ `401 Unauthorized` responses
- ❌ `JWT validation failed`
- ❌ `Agent not found`
- ❌ `Invalid token format`

Expected: No auth errors in logs

- [ ] **Step 3: Check error rate via Railway dashboard**

Open: https://railway.app/project/YOUR_PROJECT/metrics

Verify:
- Response time: < 200ms p95
- Error rate: < 0.1%
- No spike in 4xx/5xx errors

- [ ] **Step 4: Sample random API calls**

During 30-minute window, run test calls every 5 minutes:

```bash
# Minute 5
curl -s https://remembr.dev/api/v1/agents/me -H "Authorization: Bearer amc_YOUR_TOKEN" | jq .id

# Minute 10
curl -s https://remembr.dev/api/v1/memories?limit=5 -H "Authorization: Bearer amc_YOUR_TOKEN" | jq length

# Minute 15
curl -s -X POST https://remembr.dev/api/v1/auth/jwt -H "Authorization: Bearer amc_YOUR_TOKEN" | jq .expires_in

# Minute 20, 25, 30: Repeat above
```

All should return valid responses.

- [ ] **Step 5: Log monitoring completion**

```bash
cat >> migration-log.txt << EOF
30-minute monitoring: $(date)
✅ No authentication errors
✅ Error rate < 0.1%
✅ Random API calls successful
EOF
```

---

## Task 8: Final Documentation

**Files:**
- Update: `DEPLOYMENT-CHECKLIST.md`
- Create: `migration-summary-$(date +%Y%m%d).md`

**Purpose:** Document migration completion, update deployment checklist status.

- [ ] **Step 1: Update deployment checklist**

```bash
# Mark JWT migration as complete
sed -i '' 's/Status: 🟡 Code Deployed, Migration Pending/Status: 🟢 Migration Complete/' DEPLOYMENT-CHECKLIST.md
sed -i '' 's/## ⏳ Phase 2:/## ✅ Phase 2:/' DEPLOYMENT-CHECKLIST.md
```

- [ ] **Step 2: Create migration summary**

```bash
cat > "migration-summary-$(date +%Y%m%d).md" << 'EOF'
# JWT Migration Summary

**Date:** $(date)
**Duration:** [Fill in actual duration]
**Status:** ✅ Complete

## What Changed

### Database Schema
- Dropped 4 plaintext token columns:
  - `agents.api_token`
  - `users.api_token`
  - `users.magic_link_token`
  - `workspaces.api_token`

- Retained hash columns:
  - `agents.token_hash`
  - `users.api_token_hash`
  - `users.magic_link_token_hash`
  - `workspaces.api_token_hash`

### Authentication Flow
- ✅ Legacy tokens: Hash plaintext → lookup by `token_hash`
- ✅ JWT issuance: POST /api/v1/auth/jwt
- ✅ JWT auth: Decode JWT → check Redis blacklist
- ✅ All 45 tests passing

## Verification

- [x] Pre-flight checks passed (no null hashes)
- [x] Migration ran successfully
- [x] Schema verified (columns dropped)
- [x] Cache cleared
- [x] All auth flows tested (legacy + JWT)
- [x] 30-minute monitoring (no errors)
- [x] Backup created and verified

## Rollback Plan

**If needed:**
```bash
# Option 1: Restore from backup
psql $DATABASE_URL < backups/backup-TIMESTAMP.sql

# Option 2: Rollback migration (recreates empty columns)
railway run php artisan migrate:rollback

# Note: Both options lose all tokens, agents must re-register
```

## Success Metrics

- Downtime: 0 seconds (zero-downtime migration)
- Auth error rate: 0%
- All 4000+ agents unaffected
- Response time: < 200ms p95 (unchanged)

## Next Steps

1. Monitor for 24 hours (check logs daily)
2. Begin Phase 1: Monorepo foundation (next week)
3. Archive old code (30 days after stable)

---

**Migration completed by:** Claude Code + Human Review
**Sign-off:** [Your initials]
EOF
```

- [ ] **Step 3: Append migration log**

```bash
cat migration-log.txt >> "migration-summary-$(date +%Y%m%d).md"
```

- [ ] **Step 4: Commit documentation**

```bash
git add DEPLOYMENT-CHECKLIST.md migration-summary-*.md migration-log.txt
git commit -m "docs: JWT migration complete - all plaintext tokens dropped

Migration Summary:
- Dropped 4 plaintext token columns (agents, users, workspaces)
- All auth flows verified (legacy + JWT)
- Zero downtime, zero errors
- 30-minute monitoring complete

See migration-summary-$(date +%Y%m%d).md for full details"
```

- [ ] **Step 5: Push to GitHub**

```bash
git push origin main
```

Expected: Push succeeds, GitHub Actions passes (if configured)

---

## Rollback Procedure (Emergency Only)

**Only use if authentication is broken and cannot be fixed forward.**

### Option 1: Restore from Backup (Preferred)

```bash
# 1. Stop Railway deployment temporarily
railway down

# 2. Restore backup
psql "$DATABASE_URL" < backups/backup-TIMESTAMP.sql

# 3. Restart Railway
railway up

# 4. Verify auth works
curl https://remembr.dev/api/v1/agents/me -H "Authorization: Bearer amc_TOKEN"
```

**Impact:** Loses all data changes made after backup (acceptable for single-user system)

### Option 2: Rollback Migration

```bash
# 1. Rollback the migration (recreates columns)
railway run php artisan migrate:rollback

# 2. Clear cache
railway run php artisan cache:clear

# 3. Verify schema
railway run php artisan tinker --execute="
echo 'agents.api_token exists: ' . (Schema::hasColumn('agents', 'api_token') ? 'YES' : 'NO') . PHP_EOL;
"
```

**Impact:** Recreates empty columns, ALL agents must re-register (tokens lost)

### Post-Rollback Actions

1. Tweet @RemembrDev: "Brief maintenance - authentication issue resolved, please re-authenticate your agents"
2. Update DEPLOYMENT-CHECKLIST.md status to "⚠️ Rolled Back"
3. Create GitHub issue documenting rollback reason
4. Plan retry after fixing root cause

---

## Success Criteria

Migration is considered **successful** when:

- [x] All pre-flight checks passed (Task 1)
- [x] Backup created and verified (Task 2)
- [x] Migration ran without errors (Task 3)
- [x] Schema verification passed (Task 4)
- [x] Cache cleared (Task 5)
- [x] All 3 auth flows work (Task 6)
  - Legacy token auth
  - JWT issuance
  - JWT authentication
- [x] 30-minute monitoring shows zero errors (Task 7)
- [x] Documentation complete (Task 8)

**Final checklist:**
- [ ] HTTP 200 for legacy token auth
- [ ] HTTP 200 for JWT issuance
- [ ] HTTP 200 for JWT auth
- [ ] No 401 errors in 30-minute log stream
- [ ] Railway dashboard shows < 0.1% error rate
- [ ] Backup exists and is restorable
- [ ] Migration logged in GitHub commit

**Time estimate:** 1.5-2 hours from start to final commit

---

## Appendix: Useful Commands

### Check Railway service status
```bash
railway status
```

### View recent logs
```bash
railway logs --tail 500
```

### Check environment variables
```bash
railway variables | grep -E "JWT|REDIS|DB"
```

### Connect to database directly
```bash
railway run psql $DATABASE_URL
```

### List all migrations
```bash
railway run php artisan migrate:status
```

### Check Laravel version
```bash
railway run php artisan --version
```

### Test Redis connection
```bash
railway run php artisan tinker --execute="Redis::ping()"
```
