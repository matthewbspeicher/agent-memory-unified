# Migration Completion + Codebase Unification: Execution Spec

**Date:** 2026-04-05
**Status:** Approved
**Timeline:** 9 weeks (April 5 - June 7, 2026)
**Strategy:** JWT Migration (immediate) + Monorepo Unification (phases 1-6)

---

## Executive Summary

Complete security hardening by running the JWT migration, then unify agent-memory (Laravel) and stock-trading-api (Python) into a single polyglot monorepo over 9 weeks.

**What changes:**
- JWT migration drops plaintext token columns (immediate)
- Two separate repos → One monorepo with `api/`, `trading/`, `frontend/`, `shared/`
- SQLite + separate PostgreSQL → Single PostgreSQL (Laravel owns all DDL)
- Vue+Inertia + React SPA → Unified React SPA
- External API calls → Redis Streams event bus
- Duplicated models → Shared JSON Schema → generated types

**What stays the same:**
- Laravel owns memory/agent management
- Python owns trading execution
- Both services deploy independently
- Zero downtime cutover

---

## Part A: JWT Migration Execution (Immediate, April 5)

**Goal:** Run the database migration that drops plaintext token columns, verify authentication still works.

**Context:** JWT authentication code deployed on April 5, 2026 at 16:00. Migration code at `api/database/migrations/2026_04_05_200325_drop_plaintext_token_columns.php`.

### Pre-flight Verification

**Step 0: Verify hash columns are populated**
```bash
railway run php artisan tinker --execute="echo 'Agents: ' . Agent::whereNull('token_hash')->count();"
railway run php artisan tinker --execute="echo 'Users: ' . User::whereNull('api_token_hash')->count();"
railway run php artisan tinker --execute="echo 'Workspaces: ' . Workspace::whereNull('api_token_hash')->count();"
```
Expected: All return 0. If any > 0, abort and investigate.

**Step 0.5: Database backup**
```bash
railway run -- pg_dump $DATABASE_URL > backup-$(date +%Y%m%d-%H%M%S).sql
```

**Step 0.75: Verify hash-based auth already works**
```bash
curl https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer amc_YOUR_TOKEN"
```
Expected: 200 OK. Proves middleware hashes token and looks up by `token_hash`.

**Code inspection confirms:** `AppServiceProvider.php` line 55 uses `where('token_hash', hash('sha256', $token))` with no fallback to `api_token`.

### Migration Execution

**Step 1: Run migration**
```bash
railway run php artisan migrate
```

Migration drops 4 columns:
- `agents.api_token`
- `users.api_token`
- `users.magic_link_token` (replaced by `users.magic_link_token_hash`)
- `workspaces.api_token`

**Step 2: Schema verification**
```bash
railway run php artisan tinker --execute="
echo 'agents.api_token exists: ' . (Schema::hasColumn('agents', 'api_token') ? 'YES' : 'NO') . PHP_EOL;
echo 'agents.token_hash exists: ' . (Schema::hasColumn('agents', 'token_hash') ? 'YES' : 'NO') . PHP_EOL;
"
```
Expected: api_token = NO, token_hash = YES

**Step 3: Tinker smoke test**
```bash
railway run php artisan tinker --execute="
\$agent = Agent::first();
echo 'token_hash: ' . \$agent->token_hash . PHP_EOL;
echo 'api_token: ' . \$agent->api_token . PHP_EOL;
"
```
Expected: token_hash = hash string, api_token = null

**Step 4: Cache invalidation**
```bash
railway run php artisan cache:clear
```

**Step 5: Authentication flow tests**
```bash
# Legacy token auth (hashes plaintext, looks up by token_hash)
curl https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer amc_YOUR_TOKEN"

# JWT issuance
curl -X POST https://remembr.dev/api/v1/auth/jwt \
  -H "Authorization: Bearer amc_YOUR_TOKEN"

# JWT auth
curl https://remembr.dev/api/v1/agents/me \
  -H "Authorization: Bearer <JWT_FROM_STEP_2>"
```
Expected: All return 200 OK.

**Step 6: Monitor logs for 30 minutes**
```bash
railway logs -s remembr-dev --tail 100 --follow | grep -iE "auth|jwt|error|fail"
```

### Rollback Plan

If needed:
- Restore from backup: `psql $DATABASE_URL < backup-TIMESTAMP.sql`
- Or `railway run php artisan migrate:rollback` (recreates empty columns)
- All agents must re-register (acceptable, single-user system)

### Success Criteria

- ✅ All pre-flight checks pass (no null hashes)
- ✅ Migration completes without errors
- ✅ Schema verification confirms columns dropped
- ✅ All three auth test commands return 200 OK
- ✅ No authentication errors in logs for 30 minutes
- ✅ Backup exists and is restorable

**Deliverable:** Migration complete, auth verified stable

---

## Part B: Phase 0 — Python Internal Hardening (Complete)

**Status:** ✅ 100% COMPLETE (as of commit `96a4fb1`)

**What was done:**
- Fixed 2 stale `settings` references in `trading/api/app.py`
  - Line 194: `create_db(settings)` → `create_db(config)`
  - Line 577: `getattr(settings, ...)` → `getattr(config, ...)`
- Verified dependency injection complete (no global `settings` object)
- All classes accept dependencies via constructor
- Config loaded explicitly via `load_config()`

**Acceptance criteria:** ✅ All met
- No global `settings` object anywhere in Python codebase
- All classes accept dependencies via constructor
- All config loaded explicitly
- No latent runtime crashes

**No additional work needed.**

---

## Part C: Complete Codebase Unification (Phases 1-6)

**Timeline:** 9 weeks (April 5 - June 7, 2026)
**Team:** 1 developer (you)
**Phases:** 1 (Monorepo) → 2 (Database) → 3 (Event Bus) → 5 (Frontend) → 6 (Cutover)
**Phase 4 (Auth):** Already complete from Part A

### Key Architectural Decisions

**Decision 1: Keep Python table names as-is**
- **Why:** Avoids massive Python query refactor (15+ files, hundreds of queries)
- **How:** Laravel migrations create tables with Python's existing names (`tracked_positions`, `agent_registry`, etc.)
- **Trade-off:** Less "clean" naming, but saves 3-5 weeks

**Decision 2: Nginx reverse proxy for API routing**
```nginx
location /api/v1/memories { proxy_pass http://laravel:8000; }
location /api/v1/trades { proxy_pass http://python:8080; }
```
- **Why:** Single frontend baseURL, clean service separation
- **How:** Nginx routes requests to correct backend based on path
- **Trade-off:** Requires nginx config, but simplest for frontend

**Decision 3: Schema ownership = Laravel**
- All `CREATE TABLE` statements move to Laravel migrations
- Python's `init_db()` becomes `verify_schema()` (read-only checks)
- If Python needs a new table, PR adds a Laravel migration
- Single source of truth, no drift

---

## Phase 1: Monorepo Foundation (Week 1, April 5-12)

**Goal:** Set up unified repo structure with shared types. Prove tooling works, no production changes.

### 1.1: Create monorepo structure

```bash
cd /opt/homebrew/var/www/agent-memory-unified
mkdir -p shared/types/schemas
mkdir -p shared/types/generated/{python,typescript,php}
mkdir -p shared/types/scripts
```

### 1.2: Write JSON Schemas (source of truth)

**shared/types/schemas/agent.schema.json:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "Agent",
  "properties": {
    "id": {"type": "string", "format": "uuid"},
    "name": {"type": "string", "minLength": 1, "maxLength": 255},
    "owner_id": {"type": "string", "format": "uuid"},
    "is_active": {"type": "boolean"},
    "scopes": {
      "type": "array",
      "items": {"type": "string"}
    },
    "created_at": {"type": "string", "format": "date-time"},
    "updated_at": {"type": "string", "format": "date-time"}
  },
  "required": ["id", "name", "owner_id", "is_active"]
}
```

**shared/types/schemas/memory.schema.json:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "Memory",
  "properties": {
    "id": {"type": "string", "format": "uuid"},
    "agent_id": {"type": "string", "format": "uuid"},
    "value": {"type": "string"},
    "visibility": {"type": "string", "enum": ["private", "public"]},
    "embedding": {
      "type": "array",
      "items": {"type": "number"}
    },
    "created_at": {"type": "string", "format": "date-time"}
  },
  "required": ["id", "agent_id", "value", "visibility"]
}
```

**shared/types/schemas/trade.schema.json:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "Trade",
  "properties": {
    "id": {"type": "integer"},
    "agent_name": {"type": "string"},
    "symbol": {"type": "string"},
    "side": {"type": "string", "enum": ["long", "short"]},
    "entry_price": {"type": "string"},
    "entry_quantity": {"type": "integer"},
    "status": {"type": "string", "enum": ["open", "closed"]},
    "entry_time": {"type": "string", "format": "date-time"},
    "exit_time": {"type": "string", "format": "date-time", "nullable": true}
  },
  "required": ["id", "agent_name", "symbol", "side", "entry_price", "entry_quantity", "status", "entry_time"]
}
```

**shared/types/schemas/event.schema.json:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "Event",
  "properties": {
    "id": {"type": "string"},
    "type": {"type": "string"},
    "version": {"type": "string"},
    "timestamp": {"type": "string", "format": "date-time"},
    "source": {"type": "string"},
    "payload": {"type": "object"}
  },
  "required": ["id", "type", "version", "timestamp", "source", "payload"]
}
```

### 1.3: Setup type generation script

**shared/types/scripts/generate-types.sh:**
```bash
#!/bin/bash
set -e

SCHEMAS_DIR="shared/types/schemas"
OUT_PY="shared/types/generated/python"
OUT_TS="shared/types/generated/typescript"
OUT_PHP="shared/types/generated/php"

# Generate Python (Pydantic)
for schema in $SCHEMAS_DIR/*.schema.json; do
  name=$(basename "$schema" .schema.json)
  datamodel-codegen \
    --input "$schema" \
    --output "$OUT_PY/${name}.py" \
    --output-model-type pydantic_v2.BaseModel
done

# Generate TypeScript
for schema in $SCHEMAS_DIR/*.schema.json; do
  name=$(basename "$schema" .schema.json)
  quicktype "$schema" \
    --lang typescript \
    --src-lang schema \
    --out "$OUT_TS/${name}.ts"
done

# Generate PHP (TODO: pick json-schema-to-php tool)
echo "PHP generation placeholder"

echo "✅ Types generated successfully"
```

Make executable:
```bash
chmod +x shared/types/scripts/generate-types.sh
```

### 1.4: Configure Python workspace

**pyproject.toml (root):**
```toml
[tool.uv.workspace]
members = ["trading", "shared/types-py"]
```

**shared/types-py/pyproject.toml:**
```toml
[project]
name = "shared-types"
version = "0.1.0"
dependencies = ["pydantic>=2.0"]
```

**trading/pyproject.toml (add dependency):**
```toml
dependencies = [
  "shared-types @ {path = '../shared/types-py', editable = true}",
  # ... existing deps
]
```

### 1.5: Configure PHP Composer

**api/composer.json (add repository):**
```json
{
  "repositories": [
    {"type": "path", "url": "../shared/types-php"}
  ],
  "require": {
    "agent-memory/shared-types": "@dev"
  }
}
```

**shared/types-php/composer.json:**
```json
{
  "name": "agent-memory/shared-types",
  "autoload": {
    "psr-4": {
      "AgentMemory\\SharedTypes\\": "generated/php/"
    }
  }
}
```

### 1.6: Setup pre-commit hook

**.git/hooks/pre-commit:**
```bash
#!/bin/bash
./shared/types/scripts/generate-types.sh
git add shared/types/generated/
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

### Acceptance Criteria (Phase 1)

- ✅ Run `./shared/types/scripts/generate-types.sh` → sees Python/TS code generated
- ✅ Import in Python: `from shared_types import Agent`
- ✅ Import in PHP: `use AgentMemory\SharedTypes\Agent;`
- ✅ Change agent.schema.json → regenerate → see types update
- ✅ Pre-commit hook auto-generates on commit

**Deliverable:** Commit "feat: add shared types infrastructure"

---

## Phase 2: Database Consolidation (Weeks 2-5, April 13-May 10)

**Goal:** Move Python tables to PostgreSQL. **Keep existing table names** to avoid refactor.

### Week 2 (April 13-19): Schema Audit

**CRITICAL:** The Laravel migration MUST be generated from this audit, not written from memory.

**2.1: Extract Python's actual schema**
```bash
cd /opt/homebrew/var/www/agent-memory-unified/trading
grep -A 100 "CREATE TABLE" storage/db.py > ../docs/python-schema-audit.sql
```

**Example of actual Python schema (from storage/db.py lines 129-149, 378-397):**

```sql
-- tracked_positions: ACTUAL schema from db.py
CREATE TABLE IF NOT EXISTS tracked_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price TEXT NOT NULL,        -- TEXT, not DECIMAL
    entry_quantity INTEGER NOT NULL,  -- Not renamed to "quantity"
    entry_fees TEXT NOT NULL DEFAULT '0',
    entry_time TEXT NOT NULL,         -- Not renamed to "entry_at"
    exit_price TEXT,
    exit_fees TEXT,
    exit_time TEXT,                   -- Not renamed to "exit_at"
    exit_reason TEXT,
    max_adverse_excursion TEXT NOT NULL DEFAULT '0',
    status TEXT NOT NULL DEFAULT 'open',
    expires_at TEXT,
    broker_id TEXT,
    account_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
    -- NO updated_at, NO pnl, NO paper, NO metadata
);

-- agent_registry: ACTUAL schema from db.py
CREATE TABLE IF NOT EXISTS agent_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,        -- "name", not "agent_name"
    strategy TEXT NOT NULL,
    schedule TEXT NOT NULL DEFAULT 'continuous',
    interval_or_cron INTEGER NOT NULL DEFAULT 60,
    universe TEXT NOT NULL DEFAULT '[]',
    parameters TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    trust_level TEXT NOT NULL DEFAULT 'monitored',
    runtime_overrides TEXT NOT NULL DEFAULT '{}',
    promotion_criteria TEXT NOT NULL DEFAULT '{}',
    shadow_mode INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT 'human',
    parent_name TEXT,
    generation INTEGER NOT NULL DEFAULT 1,
    creation_context TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Also audit these 28+ tables:
-- trust_events, agent_overrides, backtest_results, tournament_rounds,
-- tournament_variants, llm_lessons, llm_prompt_versions, tournament_audit_log,
-- opportunities, execution_quality, shadow_executions, arb_spreads,
-- signal_features, trade_analytics, performance_snapshots,
-- bittensor_* (4 tables), consensus_*, ...
```

**2.2: Generate Laravel migration from audit**

**scripts/generate-migration-from-python.py:**
```python
import re

def sqlite_to_laravel(ddl: str) -> str:
    """Convert Python's SQLite DDL to Laravel migration syntax"""

    # Parse CREATE TABLE
    match = re.search(r'CREATE TABLE.*?(\w+)\s*\((.*?)\);', ddl, re.DOTALL)
    if not match:
        return ""

    table_name = match.group(1)
    columns = match.group(2)

    result = f"Schema::create('{table_name}', function (Blueprint $table) {{\n"

    for line in columns.split('\n'):
        line = line.strip().strip(',')
        if not line or line.startswith('--'):
            continue

        # Parse column definition
        if 'INTEGER PRIMARY KEY AUTOINCREMENT' in line:
            col_name = line.split()[0]
            result += f"    $table->id('{col_name}');\n"
        elif 'TEXT' in line:
            col_name = line.split()[0]
            nullable = 'NOT NULL' not in line
            default = None
            if 'DEFAULT' in line:
                default_match = re.search(r"DEFAULT '([^']*)'", line)
                if default_match:
                    default = default_match.group(1)

            result += f"    $table->text('{col_name}')"
            if nullable:
                result += "->nullable()"
            if default:
                result += f"->default('{default}')"
            result += ";\n"
        elif 'INTEGER' in line:
            col_name = line.split()[0]
            nullable = 'NOT NULL' not in line
            result += f"    $table->integer('{col_name}')"
            if nullable:
                result += "->nullable()"
            result += ";\n"
        elif 'REAL' in line:
            col_name = line.split()[0]
            nullable = 'NOT NULL' not in line
            result += f"    $table->decimal('{col_name}', 16, 8)"
            if nullable:
                result += "->nullable()"
            result += ";\n"

    result += "});\n\n"
    return result

# Read audit output
with open('docs/python-schema-audit.sql') as f:
    ddl = f.read()

# Generate migration for each table
tables = re.findall(r'CREATE TABLE.*?;', ddl, re.DOTALL)
print("<?php\n\nuse Illuminate\\Database\\Migrations\\Migration;")
print("use Illuminate\\Database\\Schema\\Blueprint;")
print("use Illuminate\\Support\\Facades\\Schema;\n")
print("return new class extends Migration\n{")
print("    public function up(): void\n    {")

for table_ddl in tables:
    print("        " + sqlite_to_laravel(table_ddl).replace("\n", "\n        "))

print("    }\n\n    public function down(): void\n    {")
print("        // Drop tables in reverse order")
print("    }\n};")
```

**Run:**
```bash
cd /opt/homebrew/var/www/agent-memory-unified
python3 scripts/generate-migration-from-python.py > api/database/migrations/2026_04_13_create_python_tables.php
```

**Manual review:**
- Verify types are correct (TEXT might need `->string()` with length)
- Add indexes from `CREATE INDEX` statements
- Add `down()` method to drop tables

### Week 3 (April 20-26): PostgreSQL Setup

**2.3: Verify PostgreSQL support (already exists)**

Python already has PostgreSQL support at `trading/storage/db.py` lines 9-76:
- `DatabaseConnection` class with asyncpg
- Auto-detects based on `config.database_url`
- ✅ No code changes needed

**2.4: Configure PostgreSQL connection**

**trading/.env:**
```bash
DATABASE_URL=postgresql://trading_app:PASSWORD@supabase.co:5432/agent_memory
```

**api/.env:**
```bash
DB_CONNECTION=pgsql
DB_HOST=supabase.co
DB_PORT=5432
DB_DATABASE=agent_memory
DB_USERNAME=laravel_app
DB_PASSWORD=PASSWORD
```

**2.5: Test PostgreSQL connection**

```bash
cd trading
python3 -c "
import asyncio
from config import load_config
from storage.db import DatabaseConnection

async def test():
    config = load_config()
    db_conn = DatabaseConnection(config)
    db = await db_conn.connect()
    print('✅ Connected to PostgreSQL')
    await db_conn.close()

asyncio.run(test())
"
```

**2.6: Run Laravel migration**

```bash
cd api
php artisan migrate
```

Verify:
```bash
php artisan tinker
>>> Schema::hasTable('tracked_positions')  # true
>>> Schema::hasTable('agent_registry')  # true
```

### Week 4-5 (April 27-May 10): Data Migration

**2.7: Migrate data from SQLite to PostgreSQL**

**scripts/migrate-trading-data.py:**
```python
import asyncio
import aiosqlite
import asyncpg
import os

async def migrate():
    sqlite = await aiosqlite.connect('trading/data.db')
    sqlite.row_factory = aiosqlite.Row
    pg = await asyncpg.connect(os.getenv("DATABASE_URL"))

    # Migrate tracked_positions with EXPLICIT column mapping
    print("Migrating tracked_positions...")
    cursor = await sqlite.execute("SELECT * FROM tracked_positions")
    rows = await cursor.fetchall()

    for row in rows:
        # CRITICAL: Explicit column access prevents data corruption
        await pg.execute("""
            INSERT INTO tracked_positions (
                id, agent_name, opportunity_id, symbol, side,
                entry_price, entry_quantity, entry_fees, entry_time,
                exit_price, exit_fees, exit_time, exit_reason,
                max_adverse_excursion, status, expires_at,
                broker_id, account_id, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
        """,
            row['id'],
            row['agent_name'],
            row['opportunity_id'],
            row['symbol'],
            row['side'],
            row['entry_price'],
            row['entry_quantity'],
            row['entry_fees'],
            row['entry_time'],
            row['exit_price'],
            row['exit_fees'],
            row['exit_time'],
            row['exit_reason'],
            row['max_adverse_excursion'],
            row['status'],
            row['expires_at'],
            row['broker_id'],
            row['account_id'],
            row['created_at']
        )

    print(f"  ✅ Migrated {len(rows)} rows")

    # Migrate agent_registry with explicit column mapping
    print("Migrating agent_registry...")
    cursor = await sqlite.execute("SELECT * FROM agent_registry")
    rows = await cursor.fetchall()

    for row in rows:
        await pg.execute("""
            INSERT INTO agent_registry (
                id, name, strategy, schedule, interval_or_cron,
                universe, parameters, status, trust_level,
                runtime_overrides, promotion_criteria, shadow_mode,
                created_by, parent_name, generation, creation_context,
                created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
        """,
            row['id'],
            row['name'],
            row['strategy'],
            row['schedule'],
            row['interval_or_cron'],
            row['universe'],
            row['parameters'],
            row['status'],
            row['trust_level'],
            row['runtime_overrides'],
            row['promotion_criteria'],
            row['shadow_mode'],
            row['created_by'],
            row['parent_name'],
            row['generation'],
            row['creation_context'],
            row['created_at'],
            row['updated_at']
        )

    print(f"  ✅ Migrated {len(rows)} rows")

    # Repeat for all 28 remaining tables (explicit column access)
    # trust_events, agent_overrides, backtest_results, ...

    await sqlite.close()
    await pg.close()
    print("✅ Migration complete")

if __name__ == "__main__":
    asyncio.run(migrate())
```

**Run:**
```bash
cd /opt/homebrew/var/www/agent-memory-unified
python3 scripts/migrate-trading-data.py
```

**2.8: Verify all data migrated**

```python
# Compare counts
async def verify():
    sqlite = await aiosqlite.connect('trading/data.db')
    pg = await asyncpg.connect(os.getenv("DATABASE_URL"))

    tables = ['tracked_positions', 'agent_registry', 'trading_stats', ...]
    for table in tables:
        cursor = await sqlite.execute(f"SELECT COUNT(*) FROM {table}")
        sqlite_count = (await cursor.fetchone())[0]
        pg_count = await pg.fetchval(f"SELECT COUNT(*) FROM {table}")
        print(f"{table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
        assert sqlite_count == pg_count, f"Mismatch in {table}!"

    await sqlite.close()
    await pg.close()
    print("✅ All row counts match")
```

**2.9: Switch Python to PostgreSQL**

Already configured! `DatabaseConnection` class auto-detects based on `config.database_url`.

**2.10: Run tests**

```bash
cd trading
# Tests use SQLite (config.db_path), production uses PostgreSQL
python3 -m pytest tests/ -x
```

### Acceptance Criteria (Phase 2)

- ✅ Schema audit complete (`docs/python-schema-audit.sql` exists)
- ✅ Laravel migration generated from audit (not hand-written)
- ✅ All 30+ tables exist in PostgreSQL with **exact** schema match
- ✅ Data migration uses explicit column access (no dict unpacking)
- ✅ Row counts match between SQLite and PostgreSQL
- ✅ Python code unchanged (table/column names preserved)
- ✅ Tests still pass

**Deliverable:** Commit "feat: consolidate database to PostgreSQL"

---

## Phase 3: Redis Streams Event Bus (Week 6, May 11-17)

**Status:** Python consumer already exists at `trading/events/consumer.py` ✅

**Goal:** Laravel publishes events, Python consumes them via reliable event bus.

### 3.1: Deploy Redis (if not already running)

**Railway or docker-compose.yml:**
```yaml
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
  ports:
    - "6379:6379"
  volumes:
    - redis-data:/data
```

### 3.2: Create PHP Event Publisher

**shared/events-php/src/EventPublisher.php:**
```php
<?php
namespace AgentMemory\SharedEvents;

use Illuminate\Support\Str;

class EventPublisher
{
    public function __construct(private \Redis $redis) {}

    public function publish(string $type, array $payload, array $metadata = []): void
    {
        $event = [
            'id' => Str::uuid()->toString(),  // Collision-safe UUID
            'type' => $type,
            'version' => '1.0',
            'timestamp' => now()->toIso8601String(),
            'source' => 'api',
            'payload' => $payload,
            'metadata' => $metadata,
        ];

        // MAXLEN caps stream to prevent memory exhaustion
        $this->redis->xadd('events', '*', ['data' => json_encode($event)], 10000, true);
    }
}
```

### 3.3: Register event publisher in Laravel

**api/app/Providers/AppServiceProvider.php:**
```php
use AgentMemory\SharedEvents\EventPublisher;
use Illuminate\Support\Facades\Redis;

$this->app->singleton(EventPublisher::class, function () {
    return new EventPublisher(Redis::connection()->client());
});
```

### 3.4: Publish events from Laravel

**api/app/Observers/TradeObserver.php:**
```php
<?php

namespace App\Observers;

use App\Models\Trade;
use AgentMemory\SharedEvents\EventPublisher;

class TradeObserver
{
    public function __construct(private EventPublisher $publisher) {}

    public function created(Trade $trade): void
    {
        $this->publisher->publish('trade.opened', [
            'trade_id' => $trade->id,
            'agent_id' => $trade->agent_id,
            'ticker' => $trade->ticker,
            'direction' => $trade->direction,
            'entry_price' => $trade->entry_price,
            'quantity' => $trade->quantity,
            'paper' => $trade->paper,
        ]);
    }

    public function updated(Trade $trade): void
    {
        if ($trade->status === 'closed' && $trade->wasChanged('status')) {
            $this->publisher->publish('trade.closed', [
                'trade_id' => $trade->id,
                'agent_id' => $trade->agent_id,
                'pnl' => $trade->pnl,
                'exit_price' => $trade->exit_price,
            ]);
        }
    }
}
```

**Register observer:**
```php
// api/app/Providers/AppServiceProvider.php
Trade::observe(TradeObserver::class);
```

### 3.5: Consume events in Python (already exists)

**Verify existing consumer at trading/events/consumer.py:**
```python
from events.consumer import EventConsumer

consumer = EventConsumer(redis, channel="events", group="trading-service")

@consumer.register("memory.created")
async def on_memory_created(payload: dict):
    # Index memory in local journal
    await journal_indexer.add(
        memory_id=payload["memory_id"],
        text=payload["value"],
        tags=payload.get("tags", [])
    )
```

### 3.6: Start consumer in FastAPI

**trading/api/app.py (add to lifespan):**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start event consumer
    consumer_task = asyncio.create_task(consumer.start())

    yield

    # Cleanup
    consumer_task.cancel()
```

### 3.7: Deploy DLQ monitor

**scripts/monitor-dlq.sh:**
```bash
#!/bin/bash
REDIS_URL=${REDIS_URL:-redis://localhost:6379}

DLQ_COUNT=$(redis-cli -u $REDIS_URL XLEN events:dlq)

if [ "$DLQ_COUNT" -gt 100 ]; then
  echo "⚠️  DLQ has $DLQ_COUNT failed events!"
  # Send alert via Slack/email
fi
```

Add to cron: `*/5 * * * * /app/scripts/monitor-dlq.sh`

### Acceptance Criteria (Phase 3)

- ✅ Events flow Laravel → Python
- ✅ Failed events move to DLQ after 3 retries
- ✅ No Redis OOM (MAXLEN caps stream at 10k)
- ✅ Monitor dashboard shows event lag < 1 second

**Deliverable:** Commit "feat: implement Redis Streams event bus"

---

## Phase 4: Hybrid JWT Auth (Week 5, May 4-10)

**Status:** ✅ Already complete from Part A

Verification:
- ✅ JWT issuance endpoint exists (`/api/v1/auth/jwt`)
- ✅ Python validator exists (`trading/api/dependencies.py`)
- ✅ Redis blacklist implemented
- ✅ Token revocation on deactivation

**No additional work needed.**

---

## Phase 5: Frontend Unification (Weeks 7-8, May 18-31)

**Current state:** Vue app has 14 components → 2 weeks realistic

**Goal:** Unified React SPA with nginx reverse proxy for API routing.

### 5.1: Setup nginx reverse proxy

**nginx.conf:**
```nginx
server {
    listen 80;
    server_name remembr.dev;

    # Laravel API (memories, arena, agents)
    location /api/v1/memories { proxy_pass http://api:8000; }
    location /api/v1/arena { proxy_pass http://api:8000; }
    location /api/v1/agents { proxy_pass http://api:8000; }
    location /api/v1/auth { proxy_pass http://api:8000; }

    # Python API (trading)
    location /api/v1/trades { proxy_pass http://trading:8080; }
    location /api/v1/orders { proxy_pass http://trading:8080; }

    # React frontend
    location / { proxy_pass http://frontend:3000; }
}
```

### 5.2: Scaffold React app

```bash
cd /opt/homebrew/var/www/agent-memory-unified
mkdir frontend
cd frontend
npm create vite@latest . -- --template react-ts
npm install react-router-dom@^7 @tanstack/react-query axios
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

### 5.3: Setup routing

**frontend/src/router.tsx:**
```typescript
import { createBrowserRouter } from 'react-router-dom';
import { Landing } from './pages/Landing';
import { Login } from './pages/auth/Login';
import { Dashboard } from './pages/dashboard/Dashboard';
import { TradingDashboard } from './pages/trading/TradingDashboard';
import { ArenaLeaderboard } from './pages/arena/Leaderboard';

export const router = createBrowserRouter([
  { path: '/', element: <Landing /> },
  { path: '/login', element: <Login /> },
  { path: '/dashboard', element: <Dashboard /> },
  { path: '/trading', element: <TradingDashboard /> },
  { path: '/arena', element: <ArenaLeaderboard /> },
]);
```

### 5.4: Build API client (single baseURL)

**frontend/src/lib/api/client.ts:**
```typescript
import axios from 'axios';

// Single baseURL - nginx routes to correct service
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'https://remembr.dev',
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export { api };
```

**frontend/src/lib/api/memory.ts:**
```typescript
import { api } from './client';
import type { Memory } from '@agent-memory/types';

export const memoryApi = {
  list: () => api.get<Memory[]>('/api/v1/memories'),
  search: (q: string) => api.get<Memory[]>(`/api/v1/memories/search?q=${q}`),
  create: (data: { value: string; visibility: 'private' | 'public' }) =>
    api.post<Memory>('/api/v1/memories', data),
};
```

**frontend/src/lib/api/trading.ts:**
```typescript
import { api } from './client';
import type { Trade } from '@agent-memory/types';

export const tradingApi = {
  listTrades: () => api.get<Trade[]>('/api/v1/trades'),
  openTrade: (data: { symbol: string; side: 'long' | 'short'; entry_quantity: number }) =>
    api.post<Trade>('/api/v1/trades', data),
  closeTrade: (id: number, exit_price: string) =>
    api.post<Trade>(`/api/v1/trades/${id}/close`, { exit_price }),
};
```

### 5.5: Port key pages from Vue to React

**frontend/src/pages/dashboard/Dashboard.tsx:**
```typescript
import { useQuery } from '@tanstack/react-query';
import { memoryApi } from '@/lib/api/memory';
import { MemoryCard } from '@/components/MemoryCard';

export function Dashboard() {
  const { data: memories, isLoading } = useQuery({
    queryKey: ['memories'],
    queryFn: () => memoryApi.list(),
  });

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-2xl font-bold mb-4">Memory Feed</h1>
      <div className="space-y-4">
        {memories?.data.map((memory) => (
          <MemoryCard key={memory.id} memory={memory} />
        ))}
      </div>
    </div>
  );
}
```

**frontend/src/pages/trading/TradingDashboard.tsx:**
```typescript
import { useQuery } from '@tanstack/react-query';
import { tradingApi } from '@/lib/api/trading';
import { TradeList } from '@/components/TradeList';

export function TradingDashboard() {
  const { data: trades } = useQuery({
    queryKey: ['trades'],
    queryFn: () => tradingApi.listTrades(),
  });

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-2xl font-bold mb-4">Trading Dashboard</h1>
      <TradeList trades={trades?.data || []} />
    </div>
  );
}
```

### 5.6: Add shared components

**frontend/src/components/MemoryCard.tsx:**
```typescript
import type { Memory } from '@agent-memory/types';

export function MemoryCard({ memory }: { memory: Memory }) {
  return (
    <div className="border rounded-lg p-4">
      <p className="text-gray-800">{memory.value}</p>
      <div className="mt-2 text-sm text-gray-500">
        {new Date(memory.created_at).toLocaleDateString()}
      </div>
    </div>
  );
}
```

### 5.7: Deploy frontend

**Build:**
```bash
cd frontend
npm run build
```

**Deploy to Railway:**
- Add `frontend/` to deployment config
- Set environment variable: `VITE_API_URL=https://remembr.dev`

### Acceptance Criteria (Phase 5)

- ✅ All pages from old Vue app replicated
- ✅ Trading dashboard works
- ✅ Single baseURL, nginx routes correctly
- ✅ Mobile responsive
- ✅ Lighthouse score > 90

**Deliverable:** Commit "feat: unified React frontend with nginx routing"

---

## Phase 6: Production Cutover (Week 9, June 1-7)

**Goal:** Zero-downtime cutover to unified stack.

### 6.1: Write E2E tests

**tests/e2e/trading-flow.spec.ts:**
```typescript
import { test, expect } from '@playwright/test';

test('complete trading flow', async ({ page }) => {
  // Login
  await page.goto('https://staging.remembr.dev/login');
  await page.fill('[name=email]', 'test@example.com');
  await page.fill('[name=password]', 'password');
  await page.click('button[type=submit]');

  // Open trade
  await page.goto('/trading');
  await page.click('text=New Trade');
  await page.fill('[name=symbol]', 'AAPL');
  await page.selectOption('[name=side]', 'long');
  await page.fill('[name=entry_quantity]', '100');
  await page.click('text=Submit');

  // Verify trade appears
  await expect(page.locator('text=AAPL')).toBeVisible();

  // Verify event propagation to Laravel
  await page.waitForTimeout(2000);
  await page.goto('/arena');
  await expect(page.locator('text=test@example.com')).toBeVisible();
});
```

### 6.2: Deploy to staging

```bash
# Build Docker images
docker build -t agent-memory-api:staging ./api
docker build -t agent-memory-trading:staging ./trading
docker build -t agent-memory-frontend:staging ./frontend

# Deploy to Railway staging
railway up --environment staging
```

### 6.3: Run smoke tests

```bash
npm run test:e2e -- --base-url https://staging.remembr.dev
```

### 6.4: Production cutover (simplified for single-user)

**Day 1 (June 1):** Deploy all services to production, smoke test
**Day 2:** Switch DNS to new frontend
**Day 3:** Monitor logs, verify all flows working
**Day 4-7:** Keep old stack at `/legacy` for fallback, monitor

**Rollback plan:**
- Keep old deployments running in parallel for 1 week
- DNS switch to roll back instantly
- Database backups every hour during cutover

### Acceptance Criteria (Phase 6)

- ✅ All E2E tests pass on staging
- ✅ Production cutover with <5 minutes downtime
- ✅ No data loss during migration
- ✅ Error rate < 0.1% post-deploy

**Deliverable:** "feat: complete production cutover to unified stack"

---

## Success Criteria (Overall, 9 Weeks)

**Technical:**
- ✅ Single PostgreSQL instance, both services read/write
- ✅ Redis Streams event bus with DLQ, no lost events
- ✅ Shared types prevent model drift
- ✅ JWT auth with blacklist, tokens revoked in <2 seconds
- ✅ React frontend + nginx proxy, single baseURL
- ✅ All tests pass (280+ PHP, 150+ Python, 50+ E2E)

**Operational:**
- ✅ Zero data loss during migration
- ✅ <5 minutes total downtime
- ✅ Both services deploy independently
- ✅ Can rollback within 5 minutes

**Business:**
- ✅ Feature parity with old frontends
- ✅ Page load time < 2 seconds
- ✅ Mobile responsive, Lighthouse > 90
- ✅ No regression in user experience

---

## Timeline Summary

| Week | Phase | Deliverable |
|------|-------|-------------|
| 1 (Apr 5-12) | Phase 1 | Shared types infrastructure |
| 2-5 (Apr 13-May 10) | Phase 2 | Database consolidated to PostgreSQL |
| 6 (May 11-17) | Phase 3 | Redis Streams event bus |
| 7-8 (May 18-31) | Phase 5 | React frontend + nginx |
| 9 (Jun 1-7) | Phase 6 | Production cutover |

**Phase 0:** ✅ Complete (96a4fb1)
**Phase 4:** ✅ Complete (Part A)
**Part A (JWT):** Execute immediately (April 5)

**Total: 9 weeks from April 5 → June 7, 2026**

---

## Risk Mitigation

**Risk 1: Database migration fails**
- Practice migration 3 times on staging
- Full backup before starting
- Keep old DB in read-only during cutover
- Test rollback procedure

**Risk 2: Redis runs out of memory**
- MAXLEN cap at 10k events
- Monitor with `redis-cli INFO memory`
- Alert if memory > 400MB

**Risk 3: Event bus lag**
- Monitor pending message count
- Alert if lag > 10 seconds
- Scale consumer workers if needed

**Risk 4: Frontend breaks**
- Keep old Vue app at `/legacy`
- Feature flag for new frontend
- Gradual traffic shift
- Instant DNS rollback available

---

## Post-Launch (Week 10+)

**Cleanup:**
- Delete old Vue frontend code
- Archive stock-trading-api repo on GitHub
- Update documentation and runbooks

**Monitoring:**
- Set up Grafana dashboards
- Track event bus metrics
- Monitor database performance
- Alert on error rates

**Next iteration:**
- Extract LLM service to shared library
- Add OpenTelemetry tracing
- Implement feature flags

---

**End of Specification**

*This spec consolidates Part A (JWT migration), Part B (Phase 0), and Part C (Phases 1-6) into a single execution plan. All architectural decisions approved. Ready for implementation.*
