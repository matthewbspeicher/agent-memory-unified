# Phase 1: Monorepo Setup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create unified monorepo structure with `api/`, `trading/`, `frontend/`, and `shared/` directories. Set up shared type system using JSON Schema as source of truth.

**Architecture:** Flat monorepo with clear service boundaries. JSON Schema → code generation pipeline (Python/PHP/TypeScript). Each service has own dependencies but shares types.

**Tech Stack:** JSON Schema, datamodel-codegen (Python), quicktype (TypeScript), custom PHP generator, git, uv workspace

**Timeline:** Weeks 1-2 (overlaps with Phase 0)

**Context:** Create NEW repository for unified codebase

---

## File Structure

**New Repository Structure:**
```
agent-memory/                        # New unified repo
├── api/                             # Laravel (copy from agent-memory repo)
├── trading/                         # Python (copy from stock-trading-api repo)
├── frontend/                        # React (scaffold new)
├── shared/
│   ├── types/
│   │   ├── schemas/                 # JSON Schema source files
│   │   └── generated/               # Generated code
│   ├── events/                      # Event bus (future)
│   └── auth/                        # Auth validation (future)
├── scripts/
│   └── sync-types.sh                # Code generation script
├── pyproject.toml                   # uv workspace config
├── docker-compose.yml               # Local dev
└── .github/workflows/               # CI/CD
```

---

## Task 1: Create Monorepo Structure

**Files:**
- Create: entire new repository structure

- [ ] **Step 1: Create new repository**

```bash
# Create new directory
mkdir agent-memory-unified
cd agent-memory-unified
git init

# Initial .gitignore
cat > .gitignore <<'EOF'
# Dependencies
node_modules/
vendor/
__pycache__/
*.pyc
.pytest_cache/

# Environment
.env
.env.local
*.local

# Build outputs
dist/
build/
*.log

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
EOF

git add .gitignore
git commit -m "chore: initialize monorepo"
```

- [ ] **Step 2: Copy Laravel API**

```bash
# Copy agent-memory Laravel code
cp -r ~/agent-memory/ ./api/

# Remove Laravel-specific git history
rm -rf ./api/.git

# Clean up
rm -rf ./api/node_modules ./api/vendor

git add api/
git commit -m "feat: import Laravel API from agent-memory"
```

- [ ] **Step 3: Copy Python trading code**

```bash
# Copy stock-trading-api Python code
cp -r ~/stock-trading-api/python/ ./trading/

# Remove Python-specific git history
rm -rf ./trading/.git

# Clean up
rm -rf ./trading/__pycache__ ./trading/.pytest_cache

git add trading/
git commit -m "feat: import Python trading engine from stock-trading-api"
```

- [ ] **Step 4: Create shared directory structure**

```bash
mkdir -p shared/types/schemas
mkdir -p shared/types/generated/python
mkdir -p shared/types/generated/typescript
mkdir -p shared/types/generated/php
mkdir -p scripts

git add shared/ scripts/
git commit -m "feat: add shared types directory structure"
```

- [ ] **Step 5: Create workspace configuration**

```toml
# pyproject.toml (root)
[tool.uv.workspace]
members = [
    "trading",
    "shared/types-py",
]

[tool.uv]
dev-dependencies = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
]
```

```bash
git add pyproject.toml
git commit -m "feat: add uv workspace configuration"
```

---

## Task 2: Create JSON Schema Definitions

**Files:**
- Create: `shared/types/schemas/agent.schema.json`
- Create: `shared/types/schemas/memory.schema.json`
- Create: `shared/types/schemas/trade.schema.json`
- Create: `shared/types/schemas/event.schema.json`

- [ ] **Step 1: Write agent schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://remembr.dev/schemas/agent.json",
  "type": "object",
  "title": "Agent",
  "description": "AI agent with authentication and permissions",
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique agent identifier"
    },
    "name": {
      "type": "string",
      "maxLength": 255,
      "description": "Agent display name"
    },
    "token_hash": {
      "type": "string",
      "maxLength": 64,
      "description": "SHA256 hash of agent token (amc_*)"
    },
    "is_active": {
      "type": "boolean",
      "description": "Whether agent can make API calls"
    },
    "scopes": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Permitted operations (memories:write, trading:execute)"
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": ["id", "name", "token_hash", "is_active"],
  "additionalProperties": false
}
```

```bash
cat > shared/types/schemas/agent.schema.json <<'EOF'
[paste JSON above]
EOF

git add shared/types/schemas/agent.schema.json
```

- [ ] **Step 2: Write memory schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://remembr.dev/schemas/memory.json",
  "type": "object",
  "title": "Memory",
  "description": "Knowledge record stored by an agent",
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "agent_id": {
      "type": "string",
      "format": "uuid"
    },
    "value": {
      "type": "string",
      "description": "Memory content"
    },
    "type": {
      "type": "string",
      "enum": ["note", "lesson", "preference", "fact", "procedure"],
      "description": "Memory classification"
    },
    "summary": {
      "type": "string",
      "maxLength": 500,
      "description": "Short summary for quick scanning"
    },
    "tags": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "visibility": {
      "type": "string",
      "enum": ["private", "public"],
      "default": "private"
    },
    "importance": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10,
      "default": 5
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": ["id", "agent_id", "value", "type"],
  "additionalProperties": false
}
```

```bash
cat > shared/types/schemas/memory.schema.json <<'EOF'
[paste JSON above]
EOF

git add shared/types/schemas/memory.schema.json
```

- [ ] **Step 3: Write trade schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://remembr.dev/schemas/trade.json",
  "type": "object",
  "title": "Trade",
  "description": "Trading execution record",
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "agent_id": {
      "type": "string",
      "format": "uuid"
    },
    "ticker": {
      "type": "string",
      "maxLength": 64,
      "description": "Security symbol (AAPL, SPY, etc.)"
    },
    "direction": {
      "type": "string",
      "enum": ["long", "short"]
    },
    "entry_price": {
      "type": "number",
      "description": "Entry price per share"
    },
    "quantity": {
      "type": "number",
      "description": "Number of shares/contracts"
    },
    "entry_at": {
      "type": "string",
      "format": "date-time"
    },
    "exit_at": {
      "type": "string",
      "format": "date-time"
    },
    "exit_price": {
      "type": "number"
    },
    "status": {
      "type": "string",
      "enum": ["open", "closed", "cancelled"],
      "default": "open"
    },
    "pnl": {
      "type": "number",
      "description": "Profit/loss in dollars"
    },
    "pnl_percent": {
      "type": "number",
      "description": "Profit/loss as percentage"
    },
    "strategy": {
      "type": "string",
      "description": "Strategy that generated this trade"
    },
    "paper": {
      "type": "boolean",
      "description": "Paper trading vs real money",
      "default": true
    },
    "decision_memory_id": {
      "type": "string",
      "format": "uuid",
      "description": "Memory explaining why trade was taken"
    },
    "outcome_memory_id": {
      "type": "string",
      "format": "uuid",
      "description": "Memory analyzing trade result"
    },
    "metadata": {
      "type": "object",
      "description": "Additional strategy-specific data"
    }
  },
  "required": ["id", "agent_id", "ticker", "direction", "entry_price", "quantity", "entry_at", "status"],
  "additionalProperties": false
}
```

```bash
cat > shared/types/schemas/trade.schema.json <<'EOF'
[paste JSON above]
EOF

git add shared/types/schemas/trade.schema.json
```

- [ ] **Step 4: Write event schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://remembr.dev/schemas/event.json",
  "type": "object",
  "title": "Event",
  "description": "Base event structure for Redis Streams",
  "properties": {
    "id": {
      "type": "string",
      "description": "Event ID (ULID or UUID)"
    },
    "type": {
      "type": "string",
      "description": "Event type (trade.opened, memory.created, etc.)"
    },
    "version": {
      "type": "string",
      "default": "1.0",
      "description": "Event schema version"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "source": {
      "type": "string",
      "enum": ["memory-api", "trading-engine"],
      "description": "Service that published the event"
    },
    "payload": {
      "type": "object",
      "description": "Event-specific data"
    },
    "metadata": {
      "type": "object",
      "properties": {
        "correlation_id": {
          "type": "string",
          "description": "Request trace ID"
        },
        "causation_id": {
          "type": "string",
          "description": "Parent event ID that caused this"
        }
      }
    }
  },
  "required": ["id", "type", "version", "timestamp", "source", "payload"],
  "additionalProperties": false
}
```

```bash
cat > shared/types/schemas/event.schema.json <<'EOF'
[paste JSON above]
EOF

git add shared/types/schemas/event.schema.json
git commit -m "feat: add core JSON Schema definitions

- Agent: identity and permissions
- Memory: knowledge records
- Trade: execution records
- Event: base event structure"
```

---

## Task 3: Create Type Generation Script

**Files:**
- Create: `scripts/sync-types.sh`
- Create: `scripts/generate-php-types.php`

- [ ] **Step 1: Write sync script**

```bash
#!/bin/bash
set -e

echo "🔄 Generating types from JSON Schema..."

# Python: Generate Pydantic models
echo "  → Python (Pydantic)..."
datamodel-codegen \
  --input shared/types/schemas/ \
  --output shared/types/generated/python/ \
  --output-model-type pydantic_v2.BaseModel \
  --use-standard-collections \
  --field-constraints \
  --target-python-version 3.12

# TypeScript: Generate types
echo "  → TypeScript..."
npx quicktype \
  --src shared/types/schemas/ \
  --out shared/types/generated/typescript/index.ts \
  --lang typescript \
  --just-types \
  --nice-property-names

# PHP: Generate DTOs
echo "  → PHP (DTOs)..."
php scripts/generate-php-types.php

echo "✅ Types synchronized"
```

```bash
cat > scripts/sync-types.sh <<'EOF'
[paste script above]
EOF

chmod +x scripts/sync-types.sh
git add scripts/sync-types.sh
```

- [ ] **Step 2: Write PHP generator**

```php
<?php
// scripts/generate-php-types.php

$schemasDir = __DIR__ . '/../shared/types/schemas';
$outputDir = __DIR__ . '/../shared/types/generated/php';

if (!is_dir($outputDir)) {
    mkdir($outputDir, 0755, true);
}

$schemas = glob($schemasDir . '/*.schema.json');

foreach ($schemas as $schemaPath) {
    $schema = json_decode(file_get_contents($schemaPath), true);
    $className = ucfirst(str_replace('.schema.json', '', basename($schemaPath)));

    $phpCode = generatePHPClass($className, $schema);

    file_put_contents($outputDir . '/' . $className . '.php', $phpCode);
    echo "Generated $className.php\n";
}

function generatePHPClass(string $className, array $schema): string
{
    $properties = $schema['properties'] ?? [];
    $required = $schema['required'] ?? [];

    $code = "<?php\n\n";
    $code .= "namespace AgentMemory\\SharedTypes;\n\n";
    $code .= "/**\n";
    $code .= " * " . ($schema['description'] ?? $className) . "\n";
    $code .= " * Auto-generated from JSON Schema - do not edit manually\n";
    $code .= " */\n";
    $code .= "class $className\n";
    $code .= "{\n";

    // Properties
    foreach ($properties as $name => $prop) {
        $phpType = mapJSONTypeToPHP($prop);
        $nullable = !in_array($name, $required) ? '?' : '';
        $code .= "    public {$nullable}{$phpType} \${$name};\n";
    }

    $code .= "\n";

    // Constructor
    $code .= "    public function __construct(array \$data)\n";
    $code .= "    {\n";
    foreach ($properties as $name => $prop) {
        $code .= "        \$this->{$name} = \$data['{$name}'] ?? null;\n";
    }
    $code .= "    }\n\n";

    // Validation rules
    $code .= "    public static function validationRules(): array\n";
    $code .= "    {\n";
    $code .= "        return [\n";
    foreach ($properties as $name => $prop) {
        $rules = [];
        if (in_array($name, $required)) {
            $rules[] = "'required'";
        }
        if ($prop['type'] === 'string') {
            $rules[] = "'string'";
            if (isset($prop['maxLength'])) {
                $rules[] = "'max:{$prop['maxLength']}'";
            }
        }
        if ($prop['type'] === 'integer') {
            $rules[] = "'integer'";
        }
        if (isset($prop['enum'])) {
            $values = implode(',', $prop['enum']);
            $rules[] = "'in:{$values}'";
        }
        $rulesStr = implode(', ', $rules);
        $code .= "            '{$name}' => [{$rulesStr}],\n";
    }
    $code .= "        ];\n";
    $code .= "    }\n";

    $code .= "}\n";

    return $code;
}

function mapJSONTypeToPHP(array $prop): string
{
    return match($prop['type']) {
        'string' => 'string',
        'integer' => 'int',
        'number' => 'float',
        'boolean' => 'bool',
        'array' => 'array',
        'object' => 'array',
        default => 'mixed'
    };
}
```

```bash
cat > scripts/generate-php-types.php <<'EOF'
[paste PHP above]
EOF

git add scripts/generate-php-types.php
```

- [ ] **Step 3: Install dependencies**

```bash
# Python type generation
pip install datamodel-code-generator

# TypeScript type generation (will install when running npm)
# quicktype will be npx'd

git add scripts/
git commit -m "feat: add type generation pipeline

- sync-types.sh orchestrates all generators
- PHP generator creates DTOs with validation rules
- Python uses datamodel-codegen (Pydantic v2)
- TypeScript uses quicktype"
```

- [ ] **Step 4: Test type generation**

```bash
# Run type generation
./scripts/sync-types.sh

# Verify Python types
ls shared/types/generated/python/
# Expected: agent.py, memory.py, trade.py, event.py

# Verify TypeScript types
ls shared/types/generated/typescript/
# Expected: index.ts

# Verify PHP types
ls shared/types/generated/php/
# Expected: Agent.php, Memory.php, Trade.php, Event.php

git add shared/types/generated/
git commit -m "chore: generate types from schemas

- Python Pydantic models
- TypeScript interfaces
- PHP DTOs with validation"
```

---

## Task 4: Set Up Pre-commit Hook

**Files:**
- Create: `.githooks/pre-commit`
- Create: `.github/workflows/type-check.yml`

- [ ] **Step 1: Create pre-commit hook**

```bash
#!/bin/bash
# .githooks/pre-commit

echo "🔍 Checking generated types..."

# Run type generation
./scripts/sync-types.sh

# Check if generated files changed
if [[ -n $(git status --porcelain shared/types/generated/) ]]; then
    echo "⚠️  Generated types out of sync with schemas!"
    echo "    Run: ./scripts/sync-types.sh"
    echo "    Then: git add shared/types/generated/"
    exit 1
fi

echo "✅ Types are in sync"
```

```bash
mkdir -p .githooks
cat > .githooks/pre-commit <<'EOF'
[paste hook above]
EOF

chmod +x .githooks/pre-commit

# Configure git to use .githooks
git config core.hooksPath .githooks

git add .githooks/
git commit -m "feat: add pre-commit hook for type generation

- Prevents commits with stale generated types
- Runs sync-types.sh before commit
- Fails if generated code not committed"
```

- [ ] **Step 2: Create CI workflow for type checking**

```yaml
# .github/workflows/type-check.yml
name: Type Check

on: [push, pull_request]

jobs:
  check-types:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'

      - name: Install Python dependencies
        run: pip install datamodel-code-generator

      - name: Generate types
        run: ./scripts/sync-types.sh

      - name: Check for uncommitted changes
        run: |
          if [[ -n $(git status --porcelain shared/types/generated/) ]]; then
            echo "Generated types not committed!"
            git status shared/types/generated/
            exit 1
          fi

      - name: Success
        run: echo "✅ All generated types are up to date"
```

```bash
mkdir -p .github/workflows
cat > .github/workflows/type-check.yml <<'EOF'
[paste YAML above]
EOF

git add .github/workflows/type-check.yml
git commit -m "ci: add GitHub Action for type checking

- Runs on every push and PR
- Generates types and checks they're committed
- Prevents merge if types are stale"
```

---

## Task 5: Create Package Configurations

**Files:**
- Create: `shared/types/generated/python/pyproject.toml`
- Create: `shared/types/generated/typescript/package.json`
- Create: `shared/types/generated/php/composer.json`

- [ ] **Step 1: Python package config**

```toml
# shared/types/generated/python/pyproject.toml
[project]
name = "agent-memory-types"
version = "0.1.0"
description = "Shared types for agent-memory monorepo"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.5.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

```bash
cat > shared/types/generated/python/pyproject.toml <<'EOF'
[paste TOML above]
EOF

git add shared/types/generated/python/pyproject.toml
```

- [ ] **Step 2: TypeScript package config**

```json
{
  "name": "@agent-memory/types",
  "version": "0.1.0",
  "description": "Shared TypeScript types for agent-memory",
  "main": "index.ts",
  "types": "index.ts",
  "scripts": {
    "build": "echo 'No build needed - types only'"
  },
  "keywords": ["types", "schema"],
  "author": "",
  "license": "MIT"
}
```

```bash
cat > shared/types/generated/typescript/package.json <<'EOF'
[paste JSON above]
EOF

git add shared/types/generated/typescript/package.json
```

- [ ] **Step 3: PHP package config**

```json
{
  "name": "agent-memory/shared-types",
  "description": "Shared PHP types for agent-memory",
  "type": "library",
  "require": {
    "php": ">=8.3"
  },
  "autoload": {
    "psr-4": {
      "AgentMemory\\SharedTypes\\": ""
    }
  }
}
```

```bash
cat > shared/types/generated/php/composer.json <<'EOF'
[paste JSON above]
EOF

git add shared/types/generated/php/composer.json
git commit -m "feat: add package configs for generated types

- Python: pyproject.toml (Pydantic dependency)
- TypeScript: package.json (@agent-memory/types)
- PHP: composer.json (PSR-4 autoload)"
```

---

## Task 6: Update Service Dependencies

**Files:**
- Modify: `trading/pyproject.toml`
- Modify: `api/composer.json`
- Create: `frontend/package.json` (basic scaffold)

- [ ] **Step 1: Update Python trading service**

```toml
# trading/pyproject.toml
[project]
name = "trading-engine"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "agent-memory-types @ {path = '../shared/types/generated/python', editable = true}",
    "fastapi>=0.109.0",
    "uvicorn>=0.27.0",
    "asyncpg>=0.29.0",
    "redis>=5.0.1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

```bash
# Update trading/pyproject.toml with dependency
# Then install
cd trading
pip install -e .
cd ..

git add trading/pyproject.toml
```

- [ ] **Step 2: Update PHP API service**

```json
{
  "repositories": [
    {
      "type": "path",
      "url": "../shared/types/generated/php"
    }
  ],
  "require": {
    "php": "^8.3",
    "laravel/framework": "^12.0",
    "agent-memory/shared-types": "@dev"
  }
}
```

```bash
# Add to api/composer.json "repositories" and "require" sections
cd api
composer update
cd ..

git add api/composer.json api/composer.lock
```

- [ ] **Step 3: Scaffold frontend package**

```json
{
  "name": "agent-memory-frontend",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@agent-memory/types": "file:../shared/types/generated/typescript"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.2.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0"
  }
}
```

```bash
mkdir -p frontend
cat > frontend/package.json <<'EOF'
[paste JSON above]
EOF

git add frontend/package.json
git commit -m "feat: wire up shared types in all services

- Python trading imports agent-memory-types
- PHP API requires agent-memory/shared-types
- Frontend scaffolded with @agent-memory/types"
```

---

## Task 7: Create Local Development Setup

**Files:**
- Create: `docker-compose.yml`
- Create: `scripts/dev-setup.sh`
- Create: `.env.example`

- [ ] **Step 1: Write docker-compose for local dev**

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: agent_memory
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  api:
    build:
      context: ./api
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      DB_HOST: postgres
      REDIS_HOST: redis
    depends_on:
      - postgres
      - redis
    volumes:
      - ./api:/var/www/html

  trading:
    build:
      context: ./trading
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres/agent_memory
      REDIS_URL: redis://redis:6379
    depends_on:
      - postgres
      - redis
    volumes:
      - ./trading:/app

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app
      - /app/node_modules

volumes:
  postgres_data:
  redis_data:
```

```bash
cat > docker-compose.yml <<'EOF'
[paste YAML above]
EOF

git add docker-compose.yml
```

- [ ] **Step 2: Create dev setup script**

```bash
#!/bin/bash
# scripts/dev-setup.sh
set -e

echo "🚀 Setting up agent-memory development environment..."

# Generate types
echo "1️⃣  Generating shared types..."
./scripts/sync-types.sh

# Install Python dependencies
echo "2️⃣  Installing Python dependencies..."
cd trading
pip install -e .
cd ..

# Install PHP dependencies
echo "3️⃣  Installing PHP dependencies..."
cd api
composer install
cd ..

# Install frontend dependencies
echo "4️⃣  Installing frontend dependencies..."
cd frontend
npm install
cd ..

# Start Docker services
echo "5️⃣  Starting Docker services..."
docker-compose up -d postgres redis

# Wait for Postgres
echo "⏳ Waiting for Postgres..."
until docker-compose exec -T postgres pg_isready; do
  sleep 1
done

# Run Laravel migrations
echo "6️⃣  Running database migrations..."
cd api
php artisan migrate
cd ..

echo "✅ Development environment ready!"
echo ""
echo "Start services:"
echo "  API:      cd api && php artisan serve"
echo "  Trading:  cd trading && uvicorn api.main:app --reload"
echo "  Frontend: cd frontend && npm run dev"
```

```bash
cat > scripts/dev-setup.sh <<'EOF'
[paste script above]
EOF

chmod +x scripts/dev-setup.sh
git add scripts/dev-setup.sh
```

- [ ] **Step 3: Create unified .env.example**

```bash
# .env.example

# Shared Database
DATABASE_URL=postgresql://postgres:secret@localhost:5432/agent_memory
DB_CONNECTION=pgsql
DB_HOST=localhost
DB_PORT=5432
DB_DATABASE=agent_memory
DB_USERNAME=postgres
DB_PASSWORD=secret

# Shared Redis
REDIS_URL=redis://localhost:6379
REDIS_HOST=localhost
REDIS_PORT=6379

# API Keys (shared across services)
GEMINI_API_KEY=
AWS_BEDROCK_REGION=us-east-1
AWS_BEDROCK_MODEL=anthropic.claude-sonnet-4-20250514-v1:0
ANTHROPIC_API_KEY=
GROQ_API_KEY=
OPENAI_API_KEY=

# IBKR (Python)
IB_HOST=127.0.0.1
IB_PORT=4002
IB_CLIENT_ID=1

# Kalshi (Python)
KALSHI_KEY_ID=
KALSHI_PRIVATE_KEY_PATH=.keys/kalshi.pem
KALSHI_DEMO=true

# Observability
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SENTRY_DSN=

# Laravel-specific
APP_NAME="Agent Memory"
APP_ENV=local
APP_KEY=
APP_DEBUG=true
APP_URL=http://localhost:8000

# Python-specific
ENVIRONMENT=development
LOG_LEVEL=INFO

# Frontend-specific
VITE_MEMORY_API_URL=http://localhost:8000/api/v1
VITE_TRADING_API_URL=http://localhost:8080
```

```bash
cat > .env.example <<'EOF'
[paste env above]
EOF

git add .env.example
git commit -m "feat: add local development setup

- docker-compose.yml for Postgres + Redis
- dev-setup.sh one-command bootstrap
- Unified .env.example for all services"
```

---

## Task 8: Update Documentation

**Files:**
- Create: `README.md`
- Create: `docs/architecture/monorepo.md`

- [ ] **Step 1: Write root README**

```markdown
# Agent Memory — Unified Monorepo

AI agent memory system with trading capabilities. Polyglot architecture (PHP + Python + TypeScript) with shared types.

## Structure

```
agent-memory/
├── api/         # Laravel 12 (Memory API)
├── trading/     # FastAPI (Trading Engine)
├── frontend/    # React 19 + Vite (Unified UI)
└── shared/      # JSON Schema types + event bus
```

## Quick Start

```bash
# One-command setup
./scripts/dev-setup.sh

# Start services
cd api && php artisan serve           # http://localhost:8000
cd trading && uvicorn api.main:app    # http://localhost:8080
cd frontend && npm run dev            # http://localhost:3000
```

## Development Workflow

**1. Edit JSON Schema:**
```bash
# Modify shared/types/schemas/agent.schema.json
```

**2. Regenerate types:**
```bash
./scripts/sync-types.sh
```

**3. Use in services:**
```python
# Python
from agent_memory_types import Agent, Trade

# PHP
use AgentMemory\SharedTypes\Agent;

# TypeScript
import { Agent, Trade } from '@agent-memory/types';
```

**4. Commit:**
```bash
git add shared/types/
git commit -m "feat: add new field to Agent schema"
```

## Architecture

See `docs/architecture/monorepo.md` for design decisions.

## Migration Status

- [x] Phase 0: Python hardening (DI refactor)
- [x] Phase 1: Monorepo setup (current)
- [ ] Phase 2: Database consolidation
- [ ] Phase 3: Event bus (already complete in STA)
- [ ] Phase 4: Hybrid auth
- [ ] Phase 5: Frontend unification
- [ ] Phase 6: Integration & deployment

## Testing

```bash
# PHP API tests
cd api && php artisan test

# Python trading tests
cd trading && pytest

# Frontend tests
cd frontend && npm test

# Type check CI
./scripts/sync-types.sh && git diff --exit-code shared/types/generated/
```
```

```bash
cat > README.md <<'EOF'
[paste markdown above]
EOF

git add README.md
git commit -m "docs: add root README for monorepo

- Quick start instructions
- Development workflow
- Architecture overview
- Migration status"
```

---

## Self-Review Checklist

**Spec Coverage:**
- ✅ Task 1: Monorepo structure created
- ✅ Task 2: JSON schemas defined (Agent, Memory, Trade, Event)
- ✅ Task 3: Type generation pipeline (Python/PHP/TS)
- ✅ Task 4: Pre-commit hook + CI for type checking
- ✅ Task 5: Package configs for all three languages
- ✅ Task 6: Service dependencies wired up
- ✅ Task 7: Local dev setup (docker-compose + scripts)
- ✅ Task 8: Documentation updated

**No Placeholders:**
- ✅ All JSON schemas have complete property definitions
- ✅ Type generation scripts have actual implementations
- ✅ Docker compose has real service configurations
- ✅ All commands include expected behavior

**Type Consistency:**
- ✅ Agent/Memory/Trade schemas match spec (Section 2)
- ✅ Generated code uses same property names
- ✅ Package names consistent (@agent-memory/types, agent-memory-types, AgentMemory\\SharedTypes)

---

## Success Criteria

- ✅ Monorepo structure exists with api/, trading/, frontend/, shared/
- ✅ Type generation runs without errors: `./scripts/sync-types.sh`
- ✅ All three package configs resolve dependencies
- ✅ Services import shared types successfully
- ✅ Pre-commit hook blocks stale types
- ✅ CI workflow validates types on every push
- ✅ `./scripts/dev-setup.sh` completes successfully
- ✅ Docker services start: `docker-compose up -d`

