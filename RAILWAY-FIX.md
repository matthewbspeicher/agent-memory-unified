# Railway Service Configuration Fix

## Problem
Services are deploying from wrong root directories and to asia-southeast1 instead of us-east.

## Solution (5 minutes via dashboard)

For each service, set **BOTH** root directory **AND** region:

---

### 1. API Service

URL: https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066/service/f6d0a179-55e6-4669-a040-137871efcb25/settings

- [ ] Click **Settings** (left sidebar)
- [ ] **Root Directory** → Set to: `api`
- [ ] **Region** → Change to: **us-east-1** (or us-east-4)
- [ ] Scroll to bottom → Click **Deploy** (or **Redeploy**)

---

### 2. Trading Service

URL: https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066/service/b44f6d92-76f4-4149-950f-ba13b0e6c12d/settings

- [ ] Click **Settings** (left sidebar)
- [ ] **Root Directory** → Set to: `trading`
- [ ] **Region** → Change to: **us-east-1** (or us-east-4)
- [ ] Scroll to bottom → Click **Deploy** (or **Redeploy**)

---

### 3. Frontend Service

URL: https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066/service/1a45c141-1bc5-40a5-a641-920a3e1dfb9a/settings

- [ ] Click **Settings** (left sidebar)
- [ ] **Root Directory** → Set to: `frontend`
- [ ] **Region** → Change to: **us-east-1** (or us-east-4)
- [ ] Scroll to bottom → Click **Deploy** (or **Redeploy**)

---

## Verify

After all 3 are redeployed (5-10 minutes):

```bash
cd /opt/homebrew/var/www/agent-memory-unified
railway logs --build | grep -i "region:"
```

Should show `us-east` not `asia-southeast1`.

---

## Why API Failed

Railway's GraphQL API is rejecting the mutations with "Problem processing request" errors. The dashboard is the only reliable way to set these settings right now.
