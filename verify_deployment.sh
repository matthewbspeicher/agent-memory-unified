#!/bin/bash
# Deployment Verification Script
# Tests all services are running and functional

set -e

echo "🔍 Agent Memory Commons - Deployment Verification"
echo "=================================================="
echo ""

LARAVEL_URL="${LARAVEL_URL:-http://localhost:8000}"
PYTHON_URL="${PYTHON_URL:-http://localhost:8080}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓${NC} $1"
}

fail() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# 1. Check PostgreSQL
echo "1️⃣  Checking PostgreSQL..."
if docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory -c "\dt" > /dev/null 2>&1; then
    pass "PostgreSQL is running and agent_memory database exists"
else
    fail "PostgreSQL check failed"
fi

# 2. Check Redis
echo ""
echo "2️⃣  Checking Redis..."
if redis-cli PING > /dev/null 2>&1; then
    pass "Redis is running"
else
    fail "Redis check failed"
fi

# 3. Check Laravel API
echo ""
echo "3️⃣  Checking Laravel API..."
if curl -sf "$LARAVEL_URL/api/v1/health" > /dev/null 2>&1; then
    pass "Laravel API is responding"
else
    warn "Laravel API not accessible at $LARAVEL_URL"
fi

# 4. Check Python FastAPI
echo ""
echo "4️⃣  Checking Python FastAPI..."
if curl -sf "$PYTHON_URL/health" > /dev/null 2>&1; then
    pass "Python FastAPI is responding"
else
    warn "Python API not accessible at $PYTHON_URL (may not be running)"
fi

# 5. Check Frontend
echo ""
echo "5️⃣  Checking React Frontend..."
if curl -sf "$FRONTEND_URL" > /dev/null 2>&1; then
    pass "Frontend is accessible"
else
    warn "Frontend not accessible at $FRONTEND_URL (run: cd frontend && npm run dev)"
fi

# 6. Check Event Bus
echo ""
echo "6️⃣  Checking Redis Streams..."
if redis-cli EXISTS events > /dev/null 2>&1; then
    STREAM_LEN=$(redis-cli XLEN events 2>/dev/null || echo "0")
    pass "Redis Streams ready (stream length: $STREAM_LEN)"
else
    pass "Redis Streams initialized (empty)"
fi

# 7. Check DLQ
echo ""
echo "7️⃣  Checking Dead Letter Queue..."
DLQ_LEN=$(redis-cli XLEN events:dlq 2>/dev/null || echo "0")
if [ "$DLQ_LEN" -eq "0" ]; then
    pass "DLQ is empty (good)"
else
    warn "DLQ has $DLQ_LEN messages (investigate failures)"
fi

# 8. Database migrations status
echo ""
echo "8️⃣  Checking Laravel Migrations..."
cd api
PENDING=$(php artisan migrate:status 2>/dev/null | grep -c "Pending" || echo "0")
if [ "$PENDING" -eq "0" ]; then
    pass "All migrations run"
else
    warn "$PENDING pending migrations"
fi
cd ..

# 9. Type generation
echo ""
echo "9️⃣  Checking Shared Types..."
if [ -f "shared/types/generated/python/agent.py" ] && [ -f "shared/types/generated/typescript/agent.ts" ]; then
    pass "Shared types generated"
else
    warn "Run: cd shared/types && npm run generate"
fi

# 10. Environment files
echo ""
echo "🔟 Checking Environment Files..."
if [ -f "api/.env" ]; then
    pass "Laravel .env exists"
else
    fail "api/.env missing"
fi

if [ -f "trading/.env" ]; then
    pass "Python .env exists"
else
    fail "trading/.env missing"
fi

# Summary
echo ""
echo "=================================================="
echo -e "${GREEN}✅ Verification Complete${NC}"
echo ""
echo "Next steps:"
echo "  1. Start all services:"
echo "     - Laravel: cd api && php artisan serve"
echo "     - Python:  cd trading && python3 -m uvicorn api.app:app --port 8080"
echo "     - Frontend: cd frontend && npm run dev"
echo ""
echo "  2. Test the stack:"
echo "     - Open http://localhost:3000"
echo "     - Login with an agent token"
echo "     - Create a memory"
echo "     - View trades"
echo ""
echo "  3. Monitor logs:"
echo "     - Laravel: tail -f api/storage/logs/laravel.log"
echo "     - Python: check uvicorn output"
echo "     - Redis: redis-cli MONITOR"
