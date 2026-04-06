# Production Readiness Guide

The Agent Memory Unified monorepo is now unified and ready for production-like staging.

## Final Steps for the User

### 1. Install New Dependencies
We added `3d-force-graph` for visualization and `@playwright/test` for E2E testing.
```bash
cd frontend
npm install
```

### 2. Build the Frontend
Nginx serves the static files from the `dist` directory.
```bash
cd frontend
npm run build
```

### 3. Run Staging Environment
Use the new staging compose file to test the full stack with Nginx as the gateway.
```bash
docker-compose -f staging.docker-compose.yml up -d
```
The application will be available at `http://localhost`.

### 4. Run E2E Tests
Verify the unified flow:
```bash
cd frontend
npm run test:e2e
```

## Deployment Notes
- **API (Laravel):** Ensure `REDIS_PREFIX` is empty in production env.
- **Trading (FastAPI):** `DATABASE_URL` and `REDIS_URL` must point to production instances.
- **Gateway (Nginx):** The `nginx.conf` provided handles SPA routing and API proxying.
