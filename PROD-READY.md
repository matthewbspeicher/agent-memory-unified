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

## Bittensor Validator Node

This environment is optimized for running as a **Bittensor Validator Node**. In this mode, the local Laravel API and React Frontend are disabled to minimize the node's attack surface and resource footprint.

### 1. Validator Setup
Ensure the Python environment is initialized and dependencies are installed (including vendored SDKs):
```bash
cd trading
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install ./vendor/remembr-sdk
```

### 2. Connectivity Verification
Run the dedicated verification suite to ensure the node can communicate with the shared database and Redis event bus:
```bash
# Verify Database
python verify_postgres.py

# Verify Redis Event Bus
python ../scripts/verify_event_bus.py
```

### 3. Logic Validation
Run the validator-specific test suite:
```bash
pytest tests/integration/test_bittensor_e2e.py \
       tests/unit/test_storage/test_postgres_adapter.py \
       tests/unit/test_integrations/test_bittensor_adapter.py
```

## Deployment Notes
- **API (Laravel):** For Validator nodes, the API is typically remote. Ensure `REDIS_PREFIX` is consistent across nodes.
- **Trading (FastAPI):** In Validator mode, the engine acts as the primary service. `DATABASE_URL` and `REDIS_URL` must point to local high-performance instances.
- **Gateway (Nginx):** Not required for pure Validator operation unless exposing internal metrics.

