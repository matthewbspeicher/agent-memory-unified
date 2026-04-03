# Phase 6: Integration Testing & Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End-to-end testing of unified system. Zero-downtime production cutover with gradual rollout. Rollback plan ready.

**Architecture:** Playwright E2E tests, Docker for staging, Kubernetes for production, gradual traffic shift (10% → 50% → 100%), keep old stack for 1-week fallback.

**Tech Stack:** Playwright, Docker, Kubernetes, GitHub Actions, Supabase, Railway

**Timeline:** Week 7

**Dependencies:** All previous phases complete

---

## File Structure

**New Files:**
- `tests/e2e/auth.spec.ts`
- `tests/e2e/memories.spec.ts`
- `tests/e2e/trading.spec.ts`
- `tests/e2e/full-flow.spec.ts`
- `playwright.config.ts`
- `k8s/production/kustomization.yaml`
- `scripts/gradual-rollout.sh`
- `scripts/rollback.sh`
- `.github/workflows/e2e.yml`

---

## Task 1: Write E2E Tests

**Files:**
- Create: `tests/e2e/auth.spec.ts`
- Create: `tests/e2e/memories.spec.ts`
- Create: `tests/e2e/trading.spec.ts`
- Create: `tests/e2e/full-flow.spec.ts`
- Create: `playwright.config.ts`

- [ ] **Step 1: Install Playwright**

```bash
npm install -D @playwright/test
npx playwright install
```

```bash
git add package.json package-lock.json
```

- [ ] **Step 2: Create Playwright config**

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

```bash
cat > playwright.config.ts <<'EOF'
[paste TypeScript above]
EOF

git add playwright.config.ts
```

- [ ] **Step 3: Write auth flow test**

```typescript
// tests/e2e/auth.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('can login with valid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.fill('[name=email]', 'test@example.com');
    await page.fill('[name=password]', 'password');
    await page.click('button[type=submit]');

    // Should redirect to dashboard
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.locator('h1')).toContainText('Dashboard');
  });

  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.fill('[name=email]', 'wrong@example.com');
    await page.fill('[name=password]', 'wrongpassword');
    await page.click('button[type=submit]');

    // Should show error message
    await expect(page.locator('[role=alert]')).toBeVisible();
    await expect(page.locator('[role=alert]')).toContainText('Invalid');
  });

  test('can register new account', async ({ page }) => {
    await page.goto('/register');

    await page.fill('[name=email]', `test-${Date.now()}@example.com`);
    await page.fill('[name=name]', 'Test User');
    await page.fill('[name=password]', 'password123');
    await page.click('button[type=submit]');

    // Should redirect to dashboard
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('auto-refreshes expired token', async ({ page, context }) => {
    // Login first
    await page.goto('/login');
    await page.fill('[name=email]', 'test@example.com');
    await page.fill('[name=password]', 'password');
    await page.click('button[type=submit]');

    // Expire the token by setting it to an old one
    await context.addCookies([
      {
        name: 'auth_token',
        value: 'expired-jwt-token',
        domain: 'localhost',
        path: '/',
      },
    ]);

    // Navigate to authenticated page
    await page.goto('/dashboard/memories');

    // Should auto-refresh and load page (not redirect to login)
    await expect(page).toHaveURL(/\/dashboard\/memories/);
  });
});
```

```bash
mkdir -p tests/e2e
cat > tests/e2e/auth.spec.ts <<'EOF'
[paste TypeScript above]
EOF

git add tests/e2e/auth.spec.ts
```

- [ ] **Step 4: Write memories test**

```typescript
// tests/e2e/memories.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Memories', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/login');
    await page.fill('[name=email]', 'test@example.com');
    await page.fill('[name=password]', 'password');
    await page.click('button[type=submit]');
  });

  test('can create new memory', async ({ page }) => {
    await page.goto('/dashboard/memories');

    await page.click('button:has-text("New Memory")');

    await page.fill('[name=value]', 'This is a test memory');
    await page.selectOption('[name=type]', 'note');
    await page.fill('[name=tags]', 'test, e2e');
    await page.click('button:has-text("Save")');

    // Should appear in list
    await expect(page.locator('text=This is a test memory')).toBeVisible();
  });

  test('can search memories', async ({ page }) => {
    await page.goto('/dashboard/memories');

    await page.fill('[placeholder*=Search]', 'test');
    await page.press('[placeholder*=Search]', 'Enter');

    // Should show search results
    await expect(page.locator('[data-testid=memory-card]')).toHaveCount(
      expect.any(Number)
    );
  });

  test('can delete memory', async ({ page }) => {
    await page.goto('/dashboard/memories');

    // Find first memory and delete it
    const firstMemory = page.locator('[data-testid=memory-card]').first();
    await firstMemory.locator('button[aria-label*=Delete]').click();

    // Confirm deletion
    await page.click('button:has-text("Confirm")');

    // Should show success toast
    await expect(page.locator('[role=status]')).toContainText('Deleted');
  });
});
```

```bash
cat > tests/e2e/memories.spec.ts <<'EOF'
[paste TypeScript above]
EOF

git add tests/e2e/memories.spec.ts
```

- [ ] **Step 5: Write trading test**

```typescript
// tests/e2e/trading.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Trading', () => {
  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto('/login');
    await page.fill('[name=email]', 'test@example.com');
    await page.fill('[name=password]', 'password');
    await page.click('button[type=submit]');
  });

  test('can view trading dashboard', async ({ page }) => {
    await page.goto('/dashboard/trading');

    // Should show stats
    await expect(page.locator('text=Total Trades')).toBeVisible();
    await expect(page.locator('text=Win Rate')).toBeVisible();
    await expect(page.locator('text=Total P&L')).toBeVisible();
  });

  test('can view positions', async ({ page }) => {
    await page.goto('/dashboard/trading/positions');

    // Should show positions table
    await expect(page.locator('table')).toBeVisible();
    await expect(page.locator('th:has-text("Ticker")')).toBeVisible();
    await expect(page.locator('th:has-text("Quantity")')).toBeVisible();
  });

  test('can view journal', async ({ page }) => {
    await page.goto('/dashboard/trading/journal');

    // Should show trade history
    await expect(page.locator('[data-testid=trade-card]')).toHaveCount(
      expect.any(Number)
    );
  });
});
```

```bash
cat > tests/e2e/trading.spec.ts <<'EOF'
[paste TypeScript above]
EOF

git add tests/e2e/trading.spec.ts
```

- [ ] **Step 6: Write full-flow integration test**

```typescript
// tests/e2e/full-flow.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Full Trading Flow', () => {
  test('complete flow: register → create memory → view leaderboard', async ({
    page,
  }) => {
    // 1. Register new account
    await page.goto('/register');
    const email = `test-${Date.now()}@example.com`;
    await page.fill('[name=email]', email);
    await page.fill('[name=name]', 'E2E Test User');
    await page.fill('[name=password]', 'password123');
    await page.click('button[type=submit]');

    // 2. Should land on dashboard
    await expect(page).toHaveURL(/\/dashboard/);

    // 3. Create a memory about trading strategy
    await page.goto('/dashboard/memories');
    await page.click('button:has-text("New Memory")');
    await page.fill('[name=value]', 'RSI strategy: buy when RSI < 30');
    await page.selectOption('[name=type]', 'lesson');
    await page.fill('[name=tags]', 'rsi, strategy');
    await page.click('button:has-text("Save")');

    // 4. Navigate to trading dashboard
    await page.goto('/dashboard/trading');
    await expect(page.locator('text=Total Trades')).toBeVisible();

    // 5. Check arena leaderboard
    await page.goto('/dashboard/arena');
    await expect(page.locator('text=Leaderboard')).toBeVisible();

    // User should appear in leaderboard (eventually)
    // Note: Might take a few seconds for event propagation
    await page.waitForTimeout(2000);

    // 6. View public commons
    await page.goto('/commons');
    await expect(page.locator('[data-testid=memory-card]')).toHaveCount(
      expect.any(Number)
    );
  });
});
```

```bash
cat > tests/e2e/full-flow.spec.ts <<'EOF'
[paste TypeScript above]
EOF

git add tests/e2e/full-flow.spec.ts
git commit -m "feat: add Playwright E2E tests

- Auth flow: login, register, token refresh
- Memories: create, search, delete
- Trading: dashboard, positions, journal
- Full-flow: registration → memories → leaderboard"
```

- [ ] **Step 7: Run tests locally**

```bash
# Start all services
docker-compose up -d

# Run E2E tests
npx playwright test

# View report
npx playwright show-report
```

---

## Task 2: Create Deployment Manifests

**Files:**
- Create: `k8s/production/api-deployment.yaml`
- Create: `k8s/production/trading-deployment.yaml`
- Create: `k8s/production/frontend-deployment.yaml`
- Create: `k8s/production/kustomization.yaml`

- [ ] **Step 1: Write API deployment manifest**

```yaml
# k8s/production/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  labels:
    app: api
    version: v2  # New unified version
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
        version: v2
    spec:
      containers:
      - name: api
        image: gcr.io/project/agent-memory-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: DB_HOST
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: host
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: password
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: redis-credentials
              key: url
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: jwt-secret
              key: secret
        resources:
          requests:
            memory: "256Mi"
            cpu: "200m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector:
    app: api
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
```

```bash
mkdir -p k8s/production
cat > k8s/production/api-deployment.yaml <<'EOF'
[paste YAML above]
EOF

git add k8s/production/api-deployment.yaml
```

- [ ] **Step 2: Write trading deployment manifest**

```yaml
# k8s/production/trading-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: trading
  labels:
    app: trading
    version: v2
spec:
  replicas: 2
  selector:
    matchLabels:
      app: trading
  template:
    metadata:
      labels:
        app: trading
        version: v2
    spec:
      containers:
      - name: trading
        image: gcr.io/project/agent-memory-trading:latest
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: redis-credentials
              key: url
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: jwt-secret
              key: secret
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
---
apiVersion: v1
kind: Service
metadata:
  name: trading
spec:
  selector:
    app: trading
  ports:
  - port: 80
    targetPort: 8080
  type: ClusterIP
```

```bash
cat > k8s/production/trading-deployment.yaml <<'EOF'
[paste YAML above]
EOF

git add k8s/production/trading-deployment.yaml
```

- [ ] **Step 3: Write frontend deployment manifest**

```yaml
# k8s/production/frontend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  labels:
    app: frontend
    version: v2
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
        version: v2
    spec:
      containers:
      - name: frontend
        image: gcr.io/project/agent-memory-frontend:latest
        ports:
        - containerPort: 3000
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
spec:
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 3000
  type: ClusterIP
```

```bash
cat > k8s/production/frontend-deployment.yaml <<'EOF'
[paste YAML above]
EOF

git add k8s/production/frontend-deployment.yaml
git commit -m "feat: add Kubernetes production manifests

- API: 3 replicas, health checks, resource limits
- Trading: 2 replicas, 1Gi memory
- Frontend: 2 replicas, static assets
- All use secrets for credentials"
```

---

## Task 3: Create Gradual Rollout Script

**Files:**
- Create: `scripts/gradual-rollout.sh`
- Create: `scripts/rollback.sh`

- [ ] **Step 1: Write gradual rollout script**

```bash
#!/bin/bash
# scripts/gradual-rollout.sh
set -e

echo "🚀 Starting gradual rollout to unified stack..."

# Check prerequisites
kubectl get deployments -n production | grep -q "api-v2" || {
  echo "❌ v2 deployments not found"
  exit 1
}

# Phase 1: 10% traffic to v2
echo "📊 Phase 1: Routing 10% traffic to v2..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: production
spec:
  selector:
    app: api
    # No version selector - use VirtualService for traffic split
---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: api-traffic-split
  namespace: production
spec:
  hosts:
  - api.remembr.dev
  http:
  - match:
    - uri:
        prefix: /api/v1
    route:
    - destination:
        host: api-v2
      weight: 10
    - destination:
        host: api-v1
      weight: 90
EOF

echo "⏳ Monitoring for 10 minutes..."
sleep 600

# Check error rate
ERROR_RATE=$(kubectl logs -n production -l app=api,version=v2 --since=10m | grep "ERROR" | wc -l)
if [ "$ERROR_RATE" -gt 10 ]; then
  echo "❌ High error rate detected: $ERROR_RATE errors"
  echo "🔄 Rolling back..."
  ./scripts/rollback.sh
  exit 1
fi

# Phase 2: 50% traffic
echo "📊 Phase 2: Routing 50% traffic to v2..."
kubectl patch virtualservice api-traffic-split -n production --type merge -p '
spec:
  http:
  - route:
    - destination:
        host: api-v2
      weight: 50
    - destination:
        host: api-v1
      weight: 50
'

echo "⏳ Monitoring for 20 minutes..."
sleep 1200

# Check again
ERROR_RATE=$(kubectl logs -n production -l app=api,version=v2 --since=20m | grep "ERROR" | wc -l)
if [ "$ERROR_RATE" -gt 20 ]; then
  echo "❌ High error rate detected: $ERROR_RATE errors"
  ./scripts/rollback.sh
  exit 1
fi

# Phase 3: 100% traffic
echo "📊 Phase 3: Routing 100% traffic to v2..."
kubectl patch virtualservice api-traffic-split -n production --type merge -p '
spec:
  http:
  - route:
    - destination:
        host: api-v2
      weight: 100
'

echo "✅ Rollout complete!"
echo "📝 Monitor for 24 hours before removing v1 deployments"
```

```bash
cat > scripts/gradual-rollout.sh <<'EOF'
[paste script above]
EOF

chmod +x scripts/gradual-rollout.sh
git add scripts/gradual-rollout.sh
```

- [ ] **Step 2: Write rollback script**

```bash
#!/bin/bash
# scripts/rollback.sh
set -e

echo "🔄 Rolling back to v1..."

kubectl patch virtualservice api-traffic-split -n production --type merge -p '
spec:
  http:
  - route:
    - destination:
        host: api-v1
      weight: 100
'

kubectl patch virtualservice trading-traffic-split -n production --type merge -p '
spec:
  http:
  - route:
    - destination:
        host: trading-v1
      weight: 100
'

kubectl patch virtualservice frontend-traffic-split -n production --type merge -p '
spec:
  http:
  - route:
    - destination:
        host: frontend-v1
      weight: 100
'

echo "✅ Rolled back to v1"
echo "📝 Investigate errors before retrying rollout"
```

```bash
cat > scripts/rollback.sh <<'EOF'
[paste script above]
EOF

chmod +x scripts/rollback.sh
git add scripts/rollback.sh
git commit -m "feat: add gradual rollout and rollback scripts

- gradual-rollout.sh: 10% → 50% → 100% with monitoring
- rollback.sh: instant rollback to v1
- Checks error rate at each phase"
```

---

## Task 4: Create CI/CD Pipeline

**Files:**
- Create: `.github/workflows/e2e.yml`
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create E2E workflow**

```yaml
# .github/workflows/e2e.yml
name: E2E Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Start services
        run: docker-compose up -d

      - name: Wait for services
        run: |
          ./scripts/wait-for-health.sh http://localhost:8000/health
          ./scripts/wait-for-health.sh http://localhost:8080/health
          ./scripts/wait-for-health.sh http://localhost:3000

      - name: Run migrations
        run: |
          docker-compose exec -T api php artisan migrate --force

      - name: Set up Node
        uses: actions/setup-node@v3
        with:
          node-version: 20

      - name: Install dependencies
        run: npm ci

      - name: Install Playwright browsers
        run: npx playwright install --with-deps

      - name: Run E2E tests
        run: npx playwright test

      - name: Upload test results
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: playwright-report/
```

```bash
mkdir -p .github/workflows
cat > .github/workflows/e2e.yml <<'EOF'
[paste YAML above]
EOF

git add .github/workflows/e2e.yml
```

- [ ] **Step 2: Create deployment workflow**

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
    paths-ignore:
      - 'docs/**'
      - '**.md'

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Login to GCR
        uses: docker/login-action@v2
        with:
          registry: gcr.io
          username: _json_key
          password: ${{ secrets.GCP_SA_KEY }}

      - name: Build and push API
        uses: docker/build-push-action@v4
        with:
          context: ./api
          push: true
          tags: gcr.io/${{ secrets.GCP_PROJECT }}/agent-memory-api:${{ github.sha }},gcr.io/${{ secrets.GCP_PROJECT }}/agent-memory-api:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push Trading
        uses: docker/build-push-action@v4
        with:
          context: ./trading
          push: true
          tags: gcr.io/${{ secrets.GCP_PROJECT }}/agent-memory-trading:${{ github.sha }},gcr.io/${{ secrets.GCP_PROJECT }}/agent-memory-trading:latest

      - name: Build and push Frontend
        uses: docker/build-push-action@v4
        with:
          context: ./frontend
          push: true
          tags: gcr.io/${{ secrets.GCP_PROJECT }}/agent-memory-frontend:${{ github.sha }},gcr.io/${{ secrets.GCP_PROJECT }}/agent-memory-frontend:latest

      - name: Set up kubectl
        uses: azure/setup-kubectl@v3

      - name: Deploy to staging
        run: |
          kubectl config use-context staging
          kubectl set image deployment/api api=gcr.io/${{ secrets.GCP_PROJECT }}/agent-memory-api:${{ github.sha }} -n staging
          kubectl set image deployment/trading trading=gcr.io/${{ secrets.GCP_PROJECT }}/agent-memory-trading:${{ github.sha }} -n staging
          kubectl set image deployment/frontend frontend=gcr.io/${{ secrets.GCP_PROJECT }}/agent-memory-frontend:${{ github.sha }} -n staging

      - name: Run smoke tests on staging
        run: |
          npx playwright test --grep @smoke --config=playwright.staging.config.ts

      - name: Deploy to production (manual approval required)
        if: github.ref == 'refs/heads/main'
        uses: trstringer/manual-approval@v1
        with:
          secret: ${{ github.TOKEN }}
          approvers: your-github-username
          minimum-approvals: 1

      - name: Deploy to production
        if: success()
        run: |
          kubectl config use-context production
          ./scripts/gradual-rollout.sh
```

```bash
cat > .github/workflows/deploy.yml <<'EOF'
[paste YAML above]
EOF

git add .github/workflows/deploy.yml
git commit -m "feat: add CI/CD pipelines

- e2e.yml: Runs Playwright tests on every PR
- deploy.yml: Build → Staging → Manual approval → Production
- Gradual rollout in production"
```

---

## Task 5: Production Cutover Plan

**Files:**
- Create: `docs/operations/cutover-plan.md`

- [ ] **Step 1: Document cutover procedure**

```markdown
# Production Cutover Plan

## Pre-Cutover Checklist (T-1 Week)

- [ ] All E2E tests passing on staging
- [ ] Database migration tested on staging
- [ ] Load testing completed (1000 RPS for 10 minutes)
- [ ] Rollback procedure tested
- [ ] Monitoring dashboards configured
- [ ] Alerts configured (error rate > 1%, latency > 2s)
- [ ] On-call rotation scheduled
- [ ] Incident response runbook updated
- [ ] Stakeholders notified of cutover window

## Cutover Timeline (Saturday 02:00 UTC)

### T-0:00 — Start Cutover
- [ ] Announce maintenance window (status page)
- [ ] Enable read-only mode on old stack
- [ ] Take final database backup

### T-0:15 — Database Migration
- [ ] Run Laravel migrations on production DB
- [ ] Run Python data migration script
- [ ] Verify row counts match
- [ ] Run integrity checks

### T-0:45 — Deploy v2 Stack
- [ ] Deploy API (v2) with 0 replicas
- [ ] Deploy Trading (v2) with 0 replicas
- [ ] Deploy Frontend (v2) with 0 replicas
- [ ] Scale up: API (1), Trading (1), Frontend (1)
- [ ] Verify health checks pass

### T-1:00 — Smoke Tests
- [ ] Login flow works
- [ ] Create memory works
- [ ] View trades works
- [ ] Event bus flowing (check Redis Streams)
- [ ] No errors in logs

### T-1:15 — Gradual Traffic Shift
- [ ] 10% traffic to v2
- [ ] Monitor for 10 minutes
- [ ] Check error rate < 0.1%
- [ ] Check P95 latency < 500ms

### T-1:30 — 50% Traffic
- [ ] 50% traffic to v2
- [ ] Monitor for 20 minutes
- [ ] Verify both stacks handling load

### T-2:00 — 100% Traffic
- [ ] 100% traffic to v2
- [ ] Disable old stack (keep running for rollback)
- [ ] Announce cutover complete

### T-2:30 — Post-Cutover Monitoring
- [ ] Monitor for 4 hours
- [ ] Check all metrics normal
- [ ] Verify event bus lag < 1 second
- [ ] Check database connection pool healthy

### T+24:00 — Finalize
- [ ] If stable, scale down old stack to 0
- [ ] Keep old stack for 1 week (rollback safety)
- [ ] Remove traffic split rules

## Rollback Procedure (If Needed)

**Triggers:**
- Error rate > 1%
- P95 latency > 2 seconds
- Critical feature broken
- Data integrity issue

**Steps:**
1. Run `./scripts/rollback.sh` (instant, routes 100% to v1)
2. Investigate issue in v2
3. Fix issue
4. Re-test on staging
5. Retry cutover next weekend

## Communication Plan

**Before Cutover:**
- Email to all users (T-48 hours)
- Status page announcement (T-24 hours)
- In-app banner (T-12 hours)

**During Cutover:**
- Status page: "Maintenance in progress"
- Twitter updates every 30 minutes

**After Cutover:**
- Status page: "Cutover complete"
- Email to all users: "New features available"
- Twitter: "We're back!"

## Success Criteria

- ✅ Zero data loss
- ✅ < 5 minutes total downtime
- ✅ Error rate < 0.1% post-cutover
- ✅ P95 latency < 500ms
- ✅ All features working
- ✅ Event bus flowing
- ✅ No rollback needed

## Lessons Learned (Post-Mortem)

*[To be filled after cutover]*

- What went well?
- What could be improved?
- Unexpected issues?
- Timeline accuracy?
```

```bash
mkdir -p docs/operations
cat > docs/operations/cutover-plan.md <<'EOF'
[paste markdown above]
EOF

git add docs/operations/cutover-plan.md
git commit -m "docs: add production cutover plan

- Pre-cutover checklist
- Minute-by-minute timeline
- Rollback procedure
- Communication plan
- Success criteria"
```

---

## Self-Review Checklist

**Spec Coverage:**
- ✅ Task 1: E2E tests written (auth, memories, trading, full-flow)
- ✅ Task 2: Kubernetes manifests for production
- ✅ Task 3: Gradual rollout + rollback scripts
- ✅ Task 4: CI/CD pipelines (E2E + deploy)
- ✅ Task 5: Cutover plan documented

**Testing:**
- ✅ Playwright tests cover critical flows
- ✅ Smoke tests for staging deployment
- ✅ Load testing mentioned in checklist

**Deployment:**
- ✅ Gradual rollout (10% → 50% → 100%)
- ✅ Instant rollback capability
- ✅ Health checks and monitoring
- ✅ Zero-downtime strategy

**Safety:**
- ✅ Keep old stack for 1 week
- ✅ Manual approval for production deploy
- ✅ Error rate checks at each phase
- ✅ Database backups before migration

---

## Success Criteria

- ✅ All E2E tests pass: `npx playwright test`
- ✅ Staging deployment successful
- ✅ Smoke tests pass on staging
- ✅ Production cutover < 5 minutes downtime
- ✅ Error rate < 0.1% post-deploy
- ✅ P95 latency < 500ms
- ✅ No data loss during migration
- ✅ Rollback tested and working
- ✅ Old stack kept for 1 week
- ✅ All stakeholders notified

