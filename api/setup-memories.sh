#!/bin/bash
# Setup script for storing memories in Agent Memory Commons
# Usage: ./setup-memories.sh <owner_token>

set -e

API_BASE="https://remembr.dev/api/v1"

if [ -z "$1" ]; then
    echo "Usage: ./setup-memories.sh <owner_token>"
    echo ""
    echo "Get your owner_token by registering at https://remembr.dev"
    exit 1
fi

OWNER_TOKEN="$1"
AGENT_NAME="opencode-agents-$(date +%s)"

echo "=== Agent Memory Commons Setup ==="
echo ""
echo "1. Registering agent: $AGENT_NAME"
echo ""

# Register agent
REGISTER_RESPONSE=$(curl -s -X POST "$API_BASE/agents/register" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$AGENT_NAME\",\"description\":\"OpenCode development agent\",\"owner_token\":\"$OWNER_TOKEN\"}")

echo "Response: $REGISTER_RESPONSE"
echo ""

# Extract agent token
AGENT_TOKEN=$(echo "$REGISTER_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$AGENT_TOKEN" ]; then
    echo "❌ Failed to register agent. Check your owner_token."
    exit 1
fi

echo "✅ Agent registered successfully!"
echo "Agent Token: $AGENT_TOKEN"
echo ""

# Save token to .env.local
echo "AGENT_MEMORY_TOKEN=$AGENT_TOKEN" > .env.local
echo "📝 Saved token to .env.local"

echo ""
echo "=== Storing Initial Memories ==="

# Store Identity memory
echo "Storing Identity..."
curl -s -X POST "$API_BASE/memories" \
  -H "Authorization: Bearer $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "Matthew Speicher (mspeicher) - Software Developer/Engineer. macOS user developing in /opt/homebrew/var/www/. Full-stack: Python 3.12+ async (FastAPI), PHP (Laravel), JavaScript (React 19, Vue). Prefers uv for Python deps. Configured LLM: Gemini 3.1 Pro (High).",
    "type": "fact",
    "category": "identity",
    "visibility": "private",
    "tags": ["identity", "user", "developer"]
  }' | jq -r '.id // "error"' 2>/dev/null

echo ""

# Store Career memory
echo "Storing Career..."
curl -s -X POST "$API_BASE/memories" \
  -H "Authorization: Bearer $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "Software Developer/Engineer: complex algorithm development, async concurrent Python (FastAPI, asyncio), AI integration, full-stack web dev in PHP (Laravel) and JavaScript (React 19, Vue). Prefers holistic deep-dive repository reviews to verify architectural changes.",
    "type": "fact",
    "category": "career",
    "visibility": "private",
    "tags": ["career", "skills", "developer"]
  }' | jq -r '.id // "error"' 2>/dev/null

echo ""

# Store Project: Agent Memory Commons
echo "Storing Project: Agent Memory Commons..."
curl -s -X POST "$API_BASE/memories" \
  -H "Authorization: Bearer $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "Agent Memory Commons (remembr.dev) - Persistent shared memory API for AI agents. Laravel 12/PHP 8.3, PostgreSQL + pgvector, OpenAI embeddings. Uses SSE for public feed, per-agent rate limiting (300/min), amc_ token prefix. Deployed on Railway + Supabase.",
    "type": "fact",
    "category": "projects",
    "visibility": "shared",
    "tags": ["project", "laravel", "api", "memory"]
  }' | jq -r '.id // "error"' 2>/dev/null

echo ""

# Store Project: svcs-airportal
echo "Storing Project: svcs-airportal..."
curl -s -X POST "$API_BASE/memories" \
  -H "Authorization: Bearer $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "svcs-airportal - PHP (Laravel) and Vue.js web application ecosystem. Heavy quality enforcement: Pint, Rector, PHPStan, Psalm, Vue-TSC. Run tests: ./run-tests.sh --host --skip-e2e. Recent: WelcomeUser notifications for password reset flow.",
    "type": "fact",
    "category": "projects",
    "visibility": "private",
    "tags": ["project", "laravel", "vue", "testing"]
  }' | jq -r '.id // "error"' 2>/dev/null

echo ""

# Store Project: Stock-Trading-API
echo "Storing Project: Stock-Trading-API..."
curl -s -X POST "$API_BASE/memories" \
  -H "Authorization: Bearer $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "Stock-Trading-API - Broker-agnostic algorithmic trading platform with autonomous AI agent framework. Bridges IBKR with Kalshi/Polymarket. Python 3.12+, FastAPI, React 19/TypeScript. Unified Broker Adapter pattern, execution pipeline with risk regimes, Hermes agent worker loops.",
    "type": "fact",
    "category": "projects",
    "visibility": "private",
    "tags": ["project", "trading", "python", "fastapi"]
  }' | jq -r '.id // "error"' 2>/dev/null

echo ""

# Store Preferences
echo "Storing Preferences..."
curl -s -X POST "$API_BASE/memories" \
  -H "Authorization: Bearer $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "Preferences: (1) Code commits - manual control, review before commit. (2) Python tooling - uv over pip. (3) LLM model - Gemini 3.1 Pro (High). (4) Testing - Individual tests: php artisan test --compact tests/path/to/test.php. (5) Async-first for all I/O operations. (6) Type safety: strict hints Python 3.12+, TypeScript frontend. (7) Config: Pydantic for settings, YAML schema validation.",
    "type": "preference",
    "category": "user-prefs",
    "visibility": "private",
    "tags": ["preferences", "coding-style", "testing"]
  }' | jq -r '.id // "error"' 2>/dev/null

echo ""

# Store Instructions
echo "Storing Instructions..."
curl -s -X POST "$API_BASE/memories" \
  -H "Authorization: Bearer $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "Project Instructions: svcs-airportal tests via ./run-tests.sh --host --skip-e2e (--quick to skip checks). Uses Pint, Rector, PHPStan, Psalm, Vue-TSC. Async-first all I/O ops. Type safety strict. Pydantic config. ABCs for pluggable components. Custom exceptions in python/broker/errors.py. pytest with pytest-asyncio.",
    "type": "procedure",
    "category": "instructions",
    "visibility": "private",
    "tags": ["instructions", "testing", "conventions"]
  }' | jq -r '.id // "error"' 2>/dev/null

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Agent Token saved to: .env.local"
echo "Add to your shell: export AGENT_MEMORY_TOKEN=$AGENT_TOKEN"
echo ""
echo "Search your memories: curl -H 'Authorization: Bearer $AGENT_TOKEN' '$API_BASE/memories/search?q=test'"
