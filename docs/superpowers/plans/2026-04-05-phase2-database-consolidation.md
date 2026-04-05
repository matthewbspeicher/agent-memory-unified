# Phase 2: Database Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Python's 43 SQLite tables to PostgreSQL, transfer DDL ownership to Laravel, migrate all data safely.

**Architecture:** Python already has `migrations.py` (803 lines, 45 tables Postgres DDL). Reconcile drift with `db.py`, generate Laravel migration from Postgres source, disable Python's `run_migrations()`, migrate data with explicit column mapping.

**Tech Stack:** Laravel 12 migrations, PostgreSQL (Supabase), Python asyncpg/aiosqlite, asyncio

**Timeline:** 4 weeks (Weeks 2-5, April 13-May 10, 2026)
- Week 2: Schema reconciliation
- Week 3: Laravel migration + disable Python DDL
- Weeks 4-5: Data migration + verification

**Risk Level:** High (data migration, schema ownership transfer)

---

## Pre-Execution Checklist

- [ ] Phase 1 complete (shared types infrastructure works)
- [ ] PostgreSQL connection string for Supabase ready
- [ ] SQLite database backup: `cp trading/data.db trading/data.db.backup`
- [ ] PostgreSQL backup enabled (Supabase auto-backup)
- [ ] Python's `migrations.py` exists: `ls -la trading/storage/migrations.py` (should be 803 lines)

---

## Task 1: Schema Drift Audit

**Files:**
- Read: `trading/storage/db.py` (SQLite DDL)
- Read: `trading/storage/migrations.py` (Postgres DDL)
- Read: `trading/storage/migrations/*.py` (numbered migrations)
- Create: `docs/schema-drift-audit.md`

**Purpose:** Document known schema drift between SQLite (dev) and Postgres (prod) sources before consolidation.

- [ ] **Step 1: Count tables in each source**

```bash
cd /opt/homebrew/var/www/agent-memory-unified

# SQLite (db.py)
grep -c "CREATE TABLE" trading/storage/db.py

# Postgres (migrations.py)
grep -c "CREATE TABLE" trading/storage/migrations.py
```

Expected: SQLite = 43, Postgres = 45 (2 extra)

- [ ] **Step 2: Extract table names from both sources**

```bash
# SQLite table names
grep "CREATE TABLE" trading/storage/db.py | \
  sed 's/.*CREATE TABLE[^(]*\s\+\(\w\+\).*/\1/' | \
  sort > /tmp/sqlite-tables.txt

# Postgres table names
grep "CREATE TABLE" trading/storage/migrations.py | \
  sed 's/.*CREATE TABLE[^(]*\s\+\(\w\+\).*/\1/' | \
  sort > /tmp/postgres-tables.txt

# Find differences
comm -3 /tmp/sqlite-tables.txt /tmp/postgres-tables.txt
```

Expected: Shows which 2 tables exist only in Postgres

- [ ] **Step 3: Check arb_spread_observations drift**

```bash
# SQLite has is_claimed columns (from migration 015)
grep -A30 "CREATE TABLE.*arb_spread_observations" trading/storage/db.py

# Postgres base table (check if missing)
grep -A30 "CREATE TABLE.*arb_spread_observations" trading/storage/migrations.py
```

Document: Does Postgres base have is_claimed, claimed_at, claimed_by?

- [ ] **Step 4: Check arb_trades drift**

```bash
# SQLite has sequencing column
grep -A15 "CREATE TABLE.*arb_trades" trading/storage/db.py | grep sequencing

# Postgres (check if missing)
grep -A15 "CREATE TABLE.*arb_trades" trading/storage/migrations.py | grep sequencing
```

Document: Does Postgres have sequencing column?

- [ ] **Step 5: Document all drift in audit file**

```bash
cat > docs/schema-drift-audit.md << 'EOF'
# Schema Drift Audit

**Date:** 2026-04-13
**Purpose:** Document differences between SQLite (db.py) and Postgres (migrations.py) before consolidation

## Table Count
- SQLite (db.py): 43 tables
- Postgres (migrations.py): 45 tables
- Diff: 2 extra in Postgres (likely added after fork)

## Known Drift

### 1. arb_spread_observations
**Status:** Columns added via migration 015_spread_locking.py

SQLite (db.py + migration 015):
- is_claimed BOOLEAN DEFAULT 0
- claimed_at TEXT
- claimed_by TEXT

Postgres (migrations.py base):
- ❌ Missing all 3 columns

**Fix:** Add to Postgres migration or run migration 015 against Postgres before consolidation

### 2. arb_trades
**Status:** Column exists in SQLite, missing in Postgres

SQLite (db.py):
- sequencing TEXT NOT NULL

Postgres (migrations.py):
- ❌ Missing sequencing column

**Fix:** Add to Postgres migration

### 3. JSON columns (shadow_executions, agent_registry)
**Status:** Type difference (intentional upgrade)

SQLite: TEXT with DEFAULT '{}'
Postgres: JSONB with DEFAULT '{}'

**Fix:** Keep JSONB (better for Postgres), data migration handles conversion

## Action Items

Before Laravel migration:
1. Run migration 015 against Postgres OR add columns to migrations.py
2. Add sequencing column to arb_trades in migrations.py
3. Verify no other drift via table-by-table diff

## Full Table List (43 from SQLite)

[List from spec line 865-871]

EOF

git add docs/schema-drift-audit.md
git commit -m "docs: schema drift audit before database consolidation

Documents 3 known drift issues:
- arb_spread_observations missing 3 columns (migration 015)
- arb_trades missing sequencing column
- JSON columns TEXT→JSONB (intentional upgrade)

Must fix before generating Laravel migration."
```

---

## Task 2: Reconcile Postgres Schema

**Files:**
- Modify: `trading/storage/migrations.py` (add missing columns)
- Read: `trading/storage/migrations/015_spread_locking.py`

**Purpose:** Update `migrations.py` to include all columns from SQLite + numbered migrations so it's the complete Postgres source of truth.

- [ ] **Step 1: Add missing columns to arb_spread_observations**

```bash
# Find the table definition in migrations.py
LINE=$(grep -n "CREATE TABLE.*arb_spread_observations" trading/storage/migrations.py | cut -d: -f1)

# Add columns before closing parenthesis
# (Manual edit required - find the table, add 3 columns before last closing paren)
```

Edit `trading/storage/migrations.py` line ~697:

```python
"""
CREATE TABLE IF NOT EXISTS arb_spread_observations (
    id SERIAL PRIMARY KEY,
    kalshi_ticker TEXT NOT NULL,
    poly_ticker TEXT NOT NULL,
    match_score DOUBLE PRECISION NOT NULL,
    kalshi_cents INTEGER NOT NULL,
    poly_cents INTEGER NOT NULL,
    gap_cents INTEGER NOT NULL,
    kalshi_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
    poly_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
    observed_at TEXT NOT NULL DEFAULT NOW(),
    is_claimed BOOLEAN NOT NULL DEFAULT FALSE,  -- ADD THIS
    claimed_at TEXT,                             -- ADD THIS
    claimed_by TEXT                              -- ADD THIS
)
""",
```

- [ ] **Step 2: Add sequencing column to arb_trades**

Edit `trading/storage/migrations.py` line ~711:

```python
"""
CREATE TABLE IF NOT EXISTS arb_trades (
    id TEXT PRIMARY KEY,
    symbol_a TEXT NOT NULL,
    symbol_b TEXT NOT NULL,
    expected_profit_bps INTEGER NOT NULL,
    sequencing TEXT NOT NULL,  -- ADD THIS (between expected_profit_bps and state)
    state TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT NOW(),
    updated_at TEXT NOT NULL DEFAULT NOW()
)
""",
```

- [ ] **Step 3: Verify migrations.py is now complete**

```bash
# Count columns in arb_spread_observations
grep -A20 "CREATE TABLE.*arb_spread_observations" trading/storage/migrations.py | grep -c "claimed"
```

Expected: 3 (is_claimed, claimed_at, claimed_by)

- [ ] **Step 4: Commit reconciliation**

```bash
git add trading/storage/migrations.py
git commit -m "fix(db): reconcile migrations.py with db.py and migration 015

Added missing columns:
- arb_spread_observations: is_claimed, claimed_at, claimed_by (from migration 015)
- arb_trades: sequencing (from db.py)

migrations.py now reflects complete Postgres schema including all numbered migrations."
```

---

## Task 3: Generate Laravel Migration from Postgres Source

**Files:**
- Create: `scripts/postgres-to-laravel.py`
- Create: `api/database/migrations/2026_04_13_create_trading_tables.php`

**Purpose:** Auto-generate Laravel migration from `migrations.py` (Postgres DDL), not from `db.py` (SQLite).

- [ ] **Step 1: Create conversion script**

```bash
cat > scripts/postgres-to-laravel.py << 'EOF'
#!/usr/bin/env python3
"""
Generate Laravel migration from trading/storage/migrations.py (Postgres DDL).

Reads the _STATEMENTS list, converts each CREATE TABLE to Laravel Blueprint syntax.
"""
import re
import sys

def postgres_to_blueprint(ddl: str) -> str:
    """Convert Postgres CREATE TABLE to Laravel Blueprint."""

    # Parse table name
    match = re.search(r'CREATE TABLE[^(]*\s+(\w+)\s*\(', ddl, re.IGNORECASE)
    if not match:
        return ""

    table_name = match.group(1)
    result = f"        Schema::create('{table_name}', function (Blueprint $table) {{\n"

    # Extract column definitions
    columns_match = re.search(r'\((.*)\)', ddl, re.DOTALL)
    if not columns_match:
        return result + "        });\n"

    columns_block = columns_match.group(1)

    for line in columns_block.split(','):
        line = line.strip()
        if not line or line.startswith('--') or 'REFERENCES' in line:
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        col_name = parts[0]
        col_type = parts[1]

        # Handle SERIAL PRIMARY KEY
        if col_type == 'SERIAL' and 'PRIMARY' in line:
            result += f"            $table->id('{col_name}');\n"
            continue

        # Map Postgres types to Laravel
        if col_type == 'TEXT':
            chain = f"$table->text('{col_name}')"
        elif col_type == 'INTEGER':
            chain = f"$table->integer('{col_name}')"
        elif col_type in ('DOUBLE', 'PRECISION'):
            if col_type == 'DOUBLE' and parts[2] == 'PRECISION':
                chain = f"$table->double('{col_name}')"
            else:
                chain = f"$table->double('{col_name}')"
        elif col_type == 'BOOLEAN':
            chain = f"$table->boolean('{col_name}')"
        elif col_type == 'JSONB':
            chain = f"$table->jsonb('{col_name}')"
        else:
            # Fallback: use text for unknown types
            chain = f"$table->text('{col_name}')"

        # Handle NOT NULL
        if 'NOT NULL' not in line:
            chain += "->nullable()"

        # Handle DEFAULT
        if 'DEFAULT' in line:
            # Extract default value (simplified)
            default_match = re.search(r"DEFAULT\s+([^\s,)]+)", line)
            if default_match:
                default_val = default_match.group(1)
                if default_val in ('NOW()', 'FALSE', 'TRUE', '0'):
                    if default_val == 'NOW()':
                        chain += "->useCurrent()"
                    elif default_val == 'FALSE':
                        chain += "->default(false)"
                    elif default_val == 'TRUE':
                        chain += "->default(true)"
                    elif default_val == '0':
                        chain += "->default(0)"
                elif default_val.startswith("'"):
                    chain += f"->default({default_val})"

        result += f"            {chain};\n"

    result += "        });\n"
    return result

def main():
    # Read migrations.py
    with open('trading/storage/migrations.py', 'r') as f:
        content = f.read()

    # Extract _STATEMENTS list
    statements_match = re.search(r'_STATEMENTS:\s*list\[str\]\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if not statements_match:
        print("ERROR: Could not find _STATEMENTS list", file=sys.stderr)
        sys.exit(1)

    statements_block = statements_match.group(1)

    # Split by triple-quoted strings
    tables = re.findall(r'"""(.*?)"""', statements_block, re.DOTALL)

    # Generate migration
    print("<?php\n")
    print("use Illuminate\\Database\\Migrations\\Migration;")
    print("use Illuminate\\Database\\Schema\\Blueprint;")
    print("use Illuminate\\Support\\Facades\\Schema;\n")
    print("return new class extends Migration")
    print("{")
    print("    public function up(): void")
    print("    {")

    for table_ddl in tables:
        if 'CREATE TABLE' in table_ddl:
            blueprint = postgres_to_blueprint(table_ddl)
            if blueprint:
                print(blueprint)

    # Generate indexes (simplified - just show CREATE INDEX statements as comments)
    print("\n        // Indexes")
    for stmt in re.findall(r'"(CREATE INDEX[^"]+)"', statements_block):
        print(f"        // {stmt}")

    print("    }\n")
    print("    public function down(): void")
    print("    {")
    print("        // Drop tables in reverse order")
    for table_ddl in reversed(tables):
        match = re.search(r'CREATE TABLE[^(]*\s+(\w+)', table_ddl)
        if match:
            print(f"        Schema::dropIfExists('{match.group(1)}');")
    print("    }")
    print("};")

if __name__ == '__main__':
    main()
EOF

chmod +x scripts/postgres-to-laravel.py
```

- [ ] **Step 2: Run generation**

```bash
cd /opt/homebrew/var/www/agent-memory-unified
python3 scripts/postgres-to-laravel.py > api/database/migrations/2026_04_13_000000_create_trading_tables.php
```

- [ ] **Step 3: Verify generated migration**

```bash
head -50 api/database/migrations/2026_04_13_000000_create_trading_tables.php
wc -l api/database/migrations/2026_04_13_000000_create_trading_tables.php
```

Expected: ~600-800 lines, 45 `Schema::create` calls

- [ ] **Step 4: Manual review - check sample tables**

```bash
# Verify tracked_positions matches spec
grep -A25 "Schema::create('tracked_positions'" api/database/migrations/2026_04_13_000000_create_trading_tables.php
```

Expected columns:
- id (SERIAL → id())
- agent_name (TEXT → text())
- entry_price (TEXT → text())
- entry_quantity (INTEGER → integer())

- [ ] **Step 5: Add missing indexes manually**

Edit migration file, add after all tables:

```php
        // Indexes from migrations.py
        Schema::table('opportunities', function (Blueprint $table) {
            $table->index(['agent_name', 'created_at']);
            $table->index('status');
        });

        Schema::table('tracked_positions', function (Blueprint $table) {
            $table->index(['agent_name', 'status']);
            $table->index('opportunity_id');
        });

        Schema::table('arb_spread_observations', function (Blueprint $table) {
            $table->index(['kalshi_ticker', 'poly_ticker', 'observed_at']);
            $table->index(['gap_cents', 'observed_at']);
        });

        // Add remaining indexes from grep output
```

- [ ] **Step 6: Commit generated migration**

```bash
git add scripts/postgres-to-laravel.py api/database/migrations/2026_04_13_000000_create_trading_tables.php
git commit -m "feat(db): generate Laravel migration from Python's migrations.py

Auto-generated migration for 45 trading tables:
- Source: trading/storage/migrations.py (Postgres DDL)
- Converts: SERIAL→id(), TEXT→text(), JSONB→jsonb(), etc.
- Includes: All 3 drift fix columns (is_claimed, claimed_at, claimed_by, sequencing)

Manual review complete, indexes added."
```

---

## Task 4: Configure PostgreSQL Connection

**Files:**
- Modify: `trading/.env`
- Modify: `api/.env`

**Purpose:** Configure both services to connect to same Supabase PostgreSQL database with different users.

- [ ] **Step 1: Create PostgreSQL users in Supabase**

```sql
-- Connect to Supabase via psql
psql "postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres"

-- Create Laravel user (full DDL access)
CREATE USER laravel_app WITH PASSWORD 'STRONG_PASSWORD_1';
GRANT ALL PRIVILEGES ON DATABASE agent_memory TO laravel_app;
GRANT ALL ON SCHEMA public TO laravel_app;

-- Create trading user (read/write, no DDL)
CREATE USER trading_app WITH PASSWORD 'STRONG_PASSWORD_2';
GRANT CONNECT ON DATABASE agent_memory TO trading_app;
GRANT USAGE ON SCHEMA public TO trading_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO trading_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO trading_app;

-- Auto-grant on future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO trading_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO trading_app;
```

- [ ] **Step 2: Configure Laravel .env**

```bash
cd api

# Update .env (or use Railway variables)
cat >> .env << 'EOF'

# PostgreSQL (Supabase)
DB_CONNECTION=pgsql
DB_HOST=db.PROJECT.supabase.co
DB_PORT=5432
DB_DATABASE=agent_memory
DB_USERNAME=laravel_app
DB_PASSWORD=STRONG_PASSWORD_1
EOF
```

- [ ] **Step 3: Configure Python .env**

```bash
cd trading

cat >> .env << 'EOF'

# PostgreSQL (Supabase) - trading user (no DDL)
DATABASE_URL=postgresql://trading_app:STRONG_PASSWORD_2@db.PROJECT.supabase.co:5432/agent_memory
EOF
```

- [ ] **Step 4: Test Laravel connection**

```bash
cd api
php artisan db:show
```

Expected: Shows connection to Supabase, user=laravel_app

- [ ] **Step 5: Test Python connection**

```bash
cd trading
python3 << 'EOF'
import asyncio
from config import load_config
from storage.db import DatabaseConnection

async def test():
    config = load_config()
    db_conn = DatabaseConnection(config)
    db = await db_conn.connect()

    # Run simple query
    result = await db.execute("SELECT current_database(), current_user")
    print(f"✅ Connected: {result}")

    await db_conn.close()

asyncio.run(test())
EOF
```

Expected: `✅ Connected: agent_memory, trading_app`

- [ ] **Step 6: Document connection config**

```bash
cat >> docs/schema-drift-audit.md << 'EOF'

## PostgreSQL Connection

**Database:** agent_memory on Supabase
**Users:**
- laravel_app: Full DDL (CREATE/DROP tables, migrations)
- trading_app: Read/write only (SELECT/INSERT/UPDATE/DELETE)

**Connection strings:**
- Laravel: DB_* env vars (pgsql driver)
- Python: DATABASE_URL env var (asyncpg)

EOF

git add api/.env trading/.env docs/schema-drift-audit.md
git commit -m "feat(db): configure PostgreSQL connection for both services

Two users:
- laravel_app (full DDL) for migrations
- trading_app (read/write) for runtime queries

Tested: Both services connect successfully"
```

---

## Task 5: Disable Python's run_migrations()

**Files:**
- Modify: `trading/storage/db.py` (DatabaseConnection.connect())

**Purpose:** Laravel now owns all DDL. Python should NOT auto-create tables when connecting to Postgres.

- [ ] **Step 1: Find run_migrations() call**

```bash
grep -n "run_migrations" trading/storage/db.py
```

Expected: Line ~60-70 in `DatabaseConnection.connect()`

- [ ] **Step 2: Comment out run_migrations() for Postgres**

Edit `trading/storage/db.py`:

```python
async def connect(self):
    """Connect to database (SQLite or PostgreSQL)."""
    if self.config.database_url:
        # PostgreSQL mode
        import asyncpg
        from .postgres import PostgresDB

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        pool = await asyncpg.create_pool(self.config.database_url, ssl=ssl_ctx)
        self.connection = PostgresDB(pool)

        # DISABLED: Laravel now owns all DDL via migrations
        # await run_migrations(self.connection)

        logger.info("Connected to PostgreSQL (DDL managed by Laravel)")
    else:
        # SQLite mode (dev/test)
        self.connection = await aiosqlite.connect(self.config.db_path)
        await init_db(self.connection)  # Keep for SQLite
        logger.info(f"Connected to SQLite: {self.config.db_path}")
```

- [ ] **Step 3: Archive migrations.py**

```bash
mv trading/storage/migrations.py trading/storage/migrations.py.deprecated

cat > trading/storage/migrations.py << 'EOF'
"""
DEPRECATED: This file is no longer used.

Laravel now owns all DDL via api/database/migrations/*.php

Original migrations.py preserved as migrations.py.deprecated for reference.
"""

async def run_migrations(db):
    """No-op: Laravel manages schema."""
    pass
EOF
```

- [ ] **Step 4: Test connection without auto-migration**

```bash
cd trading
python3 << 'EOF'
import asyncio
from config import load_config
from storage.db import DatabaseConnection

async def test():
    config = load_config()
    db_conn = DatabaseConnection(config)

    # Should connect WITHOUT running migrations
    db = await db_conn.connect()
    print("✅ Connected (no migrations run)")

    await db_conn.close()

asyncio.run(test())
EOF
```

Expected: `✅ Connected (no migrations run)` (no SQL errors)

- [ ] **Step 5: Commit changes**

```bash
git add trading/storage/db.py trading/storage/migrations.py trading/storage/migrations.py.deprecated
git commit -m "feat(db): disable Python's run_migrations() - Laravel owns DDL

Changes:
- db.py: Comment out run_migrations() for Postgres mode
- migrations.py: Replaced with deprecation notice
- migrations.py.deprecated: Archived original (803 lines)

SQLite mode unchanged (dev/test still auto-creates tables)"
```

---

## Task 6: Run Laravel Migration

**Files:**
- Execute: `api/database/migrations/2026_04_13_000000_create_trading_tables.php`

**Purpose:** Create all 45 trading tables in PostgreSQL via Laravel.

- [ ] **Step 1: Run migration in development first**

```bash
cd api
php artisan migrate
```

Expected output shows 45 tables created

- [ ] **Step 2: Verify tables exist**

```bash
php artisan tinker << 'EOF'
use Illuminate\Support\Facades\Schema;

$tables = DB::select("SELECT tablename FROM pg_tables WHERE schemaname = 'public'");
$count = count(array_filter($tables, fn($t) => !str_starts_with($t->tablename, 'migrations')));

echo "✅ Tables created: {$count}\n";

// Check specific tables
echo "tracked_positions exists: " . (Schema::hasTable('tracked_positions') ? 'YES' : 'NO') . "\n";
echo "agent_registry exists: " . (Schema::hasTable('agent_registry') ? 'YES' : 'NO') . "\n";
echo "arb_spread_observations exists: " . (Schema::hasTable('arb_spread_observations') ? 'YES' : 'NO') . "\n";
EOF
```

Expected:
```
✅ Tables created: 45
tracked_positions exists: YES
agent_registry exists: YES
arb_spread_observations exists: YES
```

- [ ] **Step 3: Verify drift columns present**

```bash
php artisan tinker << 'EOF'
use Illuminate\Support\Facades\Schema;

// Check arb_spread_observations has drift columns
$columns = Schema::getColumnListing('arb_spread_observations');
echo "is_claimed: " . (in_array('is_claimed', $columns) ? 'YES ✅' : 'NO ❌') . "\n";
echo "claimed_at: " . (in_array('claimed_at', $columns) ? 'YES ✅' : 'NO ❌') . "\n";
echo "claimed_by: " . (in_array('claimed_by', $columns) ? 'YES ✅' : 'NO ❌') . "\n";

// Check arb_trades has sequencing
$columns = Schema::getColumnListing('arb_trades');
echo "sequencing: " . (in_array('sequencing', $columns) ? 'YES ✅' : 'NO ❌') . "\n";
EOF
```

Expected: All 4 columns present (✅)

- [ ] **Step 4: Test Python can query tables**

```bash
cd trading
python3 << 'EOF'
import asyncio
from config import load_config
from storage.db import DatabaseConnection

async def test():
    config = load_config()
    db_conn = DatabaseConnection(config)
    db = await db_conn.connect()

    # Query empty table (should work, return 0 rows)
    count = await db.fetchval("SELECT COUNT(*) FROM tracked_positions")
    print(f"✅ Python can query tracked_positions: {count} rows")

    await db_conn.close()

asyncio.run(test())
EOF
```

Expected: `✅ Python can query tracked_positions: 0 rows`

- [ ] **Step 5: Commit migration success**

```bash
git add -A
git commit -m "feat(db): run Laravel migration - 45 trading tables created

Migration 2026_04_13_000000_create_trading_tables.php:
- Created all 45 tables from Python's migrations.py
- Verified drift columns present (is_claimed, sequencing)
- Python can query tables (trading_app user has SELECT)

Next: Data migration from SQLite to Postgres"
```

---

## Task 7: Data Migration Script (Week 4)

**Files:**
- Create: `scripts/migrate-trading-data.py`

**Purpose:** Migrate all data from SQLite to PostgreSQL with explicit column mapping to prevent corruption.

- [ ] **Step 1: Create migration script skeleton**

```bash
cat > scripts/migrate-trading-data.py << 'EOF'
#!/usr/bin/env python3
"""
Migrate trading data from SQLite to PostgreSQL.

CRITICAL: Uses explicit column access (row['column_name']) to prevent
data corruption from column order mismatches.
"""
import asyncio
import aiosqlite
import asyncpg
import os
import sys
from typing import List, Tuple

# Table definitions (table_name, column_list)
TABLES: List[Tuple[str, List[str]]] = [
    ('tracked_positions', [
        'id', 'agent_name', 'opportunity_id', 'symbol', 'side',
        'entry_price', 'entry_quantity', 'entry_fees', 'entry_time',
        'exit_price', 'exit_fees', 'exit_time', 'exit_reason',
        'max_adverse_excursion', 'status', 'expires_at',
        'broker_id', 'account_id', 'created_at'
    ]),
    ('agent_registry', [
        'id', 'name', 'strategy', 'schedule', 'interval_or_cron',
        'universe', 'parameters', 'status', 'trust_level',
        'runtime_overrides', 'promotion_criteria', 'shadow_mode',
        'created_by', 'parent_name', 'generation', 'creation_context',
        'created_at', 'updated_at'
    ]),
    # Add remaining 41 tables here...
]

async def migrate_table(sqlite: aiosqlite.Connection, pg: asyncpg.Connection, table_name: str, columns: List[str]):
    """Migrate one table with explicit column mapping."""
    print(f"\n→ Migrating {table_name}...")

    # Fetch all rows
    sqlite.row_factory = aiosqlite.Row
    cursor = await sqlite.execute(f"SELECT * FROM {table_name}")
    rows = await cursor.fetchall()

    if not rows:
        print(f"  ⚠️  Empty table, skipping")
        return

    # Build INSERT with explicit columns
    placeholders = ', '.join([f'${i+1}' for i in range(len(columns))])
    insert_sql = f"""
        INSERT INTO {table_name} ({', '.join(columns)})
        VALUES ({placeholders})
    """

    # Insert each row with explicit column access
    for row in rows:
        values = [row[col] for col in columns]
        await pg.execute(insert_sql, *values)

    print(f"  ✅ Migrated {len(rows)} rows")

async def main():
    sqlite_path = os.getenv('SQLITE_PATH', 'trading/data.db')
    postgres_url = os.getenv('DATABASE_URL')

    if not postgres_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    print(f"Migrating from {sqlite_path} to PostgreSQL...")

    # Connect to both databases
    sqlite = await aiosqlite.connect(sqlite_path)
    pg = await asyncpg.connect(postgres_url)

    try:
        # Migrate each table
        for table_name, columns in TABLES:
            await migrate_table(sqlite, pg, table_name, columns)

        print("\n✅ Migration complete")

    finally:
        await sqlite.close()
        await pg.close()

if __name__ == '__main__':
    asyncio.run(main())
EOF

chmod +x scripts/migrate-trading-data.py
```

- [ ] **Step 2: Add all 43 table definitions**

Edit `TABLES` list in `scripts/migrate-trading-data.py`, add remaining tables from spec line 865-871. For each table:
1. Look up columns in `trading/storage/db.py` CREATE TABLE
2. List ALL columns in order
3. Use explicit list, NO wildcards

(This step is manual - spec shows 43 tables, each needs column list extracted from db.py)

- [ ] **Step 3: Test migration on first 2 tables only**

```bash
# Temporarily edit script to only migrate first 2 tables
# (Comment out lines after agent_registry in TABLES list)

cd /opt/homebrew/var/www/agent-memory-unified
SQLITE_PATH=trading/data.db DATABASE_URL="postgresql://..." python3 scripts/migrate-trading-data.py
```

Expected:
```
→ Migrating tracked_positions...
  ✅ Migrated X rows
→ Migrating agent_registry...
  ✅ Migrated Y rows
✅ Migration complete
```

- [ ] **Step 4: Verify migrated data**

```bash
cd api
php artisan tinker << 'EOF'
$count = DB::table('tracked_positions')->count();
echo "tracked_positions: {$count} rows\n";

$count = DB::table('agent_registry')->count();
echo "agent_registry: {$count} rows\n";
EOF
```

- [ ] **Step 5: Commit migration script (partial)**

```bash
git add scripts/migrate-trading-data.py
git commit -m "wip(db): create data migration script (2 tables tested)

Explicit column mapping prevents data corruption:
- row['column_name'] NOT dict unpacking
- Tested: tracked_positions, agent_registry
- TODO: Add remaining 41 tables to TABLES list

Do NOT run full migration until all 43 tables added."
```

---

## Task 8: Complete Migration Script (Week 4-5 continuation)

**Files:**
- Modify: `scripts/migrate-trading-data.py` (add all 43 tables)

**Purpose:** Finish migration script with all table definitions extracted from `db.py`.

- [ ] **Step 1: Extract columns for remaining tables**

For each of these 41 tables, run:

```bash
# Example for opportunities table
grep -A30 "CREATE TABLE.*opportunities" trading/storage/db.py | \
  grep -E "^\s+\w+\s+" | \
  awk '{print $1}' | \
  tr '\n' ',' | \
  sed 's/,$//'
```

Output is comma-separated column list → add to TABLES in migration script

Tables to process:
```
opportunities, trades, risk_events, performance_snapshots,
opportunity_snapshots, whatsapp_sessions, trust_events,
agent_overrides, backtest_results, tournament_rounds,
tournament_variants, llm_lessons, llm_prompt_versions,
tournament_audit_log, agent_stages, external_positions,
external_balances, consensus_votes, leaderboard_cache,
agent_remembr_map, trade_autopsies, daily_briefs,
convergence_syntheses, execution_quality, shadow_executions,
position_exit_rules, arb_spread_observations, arb_trades,
arb_legs, bittensor_raw_forecasts, bittensor_derived_views,
bittensor_realized_windows, bittensor_accuracy_records,
bittensor_miner_rankings, execution_cost_events,
execution_cost_stats, trade_analytics,
strategy_confidence_calibration, strategy_health,
strategy_health_events, signal_features
```

- [ ] **Step 2: Verify all 43 tables defined**

```bash
grep -c "^    ('" scripts/migrate-trading-data.py
```

Expected: 43

- [ ] **Step 3: Run full migration (dry-run first)**

Add `--dry-run` flag to script:

```python
async def main():
    # ... existing code ...

    dry_run = '--dry-run' in sys.argv

    for table_name, columns in TABLES:
        if dry_run:
            print(f"Would migrate: {table_name}")
        else:
            await migrate_table(sqlite, pg, table_name, columns)
```

Run dry-run:

```bash
python3 scripts/migrate-trading-data.py --dry-run
```

Expected: Shows all 43 tables would be migrated

- [ ] **Step 4: Run actual migration**

```bash
# Backup SQLite first
cp trading/data.db trading/data.db.pre-migration-backup

# Run migration
DATABASE_URL="postgresql://..." python3 scripts/migrate-trading-data.py
```

Expected: All 43 tables migrated successfully

- [ ] **Step 5: Commit completed script**

```bash
git add scripts/migrate-trading-data.py
git commit -m "feat(db): complete data migration script - all 43 tables

All tables now defined with explicit column mapping:
- 43 tables from SQLite → Postgres
- Explicit row['column'] access (no unpacking)
- Tested: Dry-run → actual migration successful

Migration script ready for production use."
```

---

## Task 9: Verification (Week 5)

**Files:**
- Create: `scripts/verify-migration.py`

**Purpose:** Verify row counts match between SQLite and PostgreSQL for all 43 tables.

- [ ] **Step 1: Create verification script**

```bash
cat > scripts/verify-migration.py << 'EOF'
#!/usr/bin/env python3
"""Verify data migration: Compare row counts SQLite vs Postgres."""
import asyncio
import aiosqlite
import asyncpg
import os
import sys

TABLES = [
    'opportunities', 'trades', 'risk_events', # ... all 43 tables
]

async def verify():
    sqlite = await aiosqlite.connect('trading/data.db')
    pg = await asyncpg.connect(os.getenv('DATABASE_URL'))

    mismatches = []

    for table in TABLES:
        sqlite_count = (await sqlite.execute(f"SELECT COUNT(*) FROM {table}")).fetchone()[0]
        pg_count = await pg.fetchval(f"SELECT COUNT(*) FROM {table}")

        status = "✅" if sqlite_count == pg_count else "❌"
        print(f"{status} {table}: SQLite={sqlite_count}, Postgres={pg_count}")

        if sqlite_count != pg_count:
            mismatches.append(table)

    await sqlite.close()
    await pg.close()

    if mismatches:
        print(f"\n❌ Mismatches found in: {', '.join(mismatches)}")
        sys.exit(1)
    else:
        print("\n✅ All row counts match!")

asyncio.run(verify())
EOF

chmod +x scripts/verify-migration.py
```

- [ ] **Step 2: Run verification**

```bash
DATABASE_URL="postgresql://..." python3 scripts/verify-migration.py
```

Expected: All tables show ✅ with matching counts

- [ ] **Step 3: Sample data spot checks**

```bash
# Verify first row of tracked_positions
psql "$DATABASE_URL" << 'EOF'
SELECT id, agent_name, symbol, side, entry_price, status FROM tracked_positions LIMIT 1;
EOF

# Compare with SQLite
sqlite3 trading/data.db << 'EOF'
SELECT id, agent_name, symbol, side, entry_price, status FROM tracked_positions LIMIT 1;
EOF
```

Values should match exactly.

- [ ] **Step 4: Verify JSON columns migrated correctly**

```bash
psql "$DATABASE_URL" << 'EOF'
SELECT name, parameters::jsonb FROM agent_registry WHERE parameters != '{}' LIMIT 1;
EOF
```

Expected: Valid JSON, not TEXT string

- [ ] **Step 5: Commit verification script**

```bash
git add scripts/verify-migration.py
git commit -m "test(db): add migration verification script

Compares row counts across all 43 tables:
- SQLite vs Postgres
- Flags mismatches
- Sample data spot checks

Run after migration to verify completeness."
```

---

## Task 10: Switch Python to Postgres

**Files:**
- Modify: `trading/.env` (switch DATABASE_URL to Postgres)
- Test: Python queries work against Postgres

**Purpose:** Point trading service at PostgreSQL, verify it works with migrated data.

- [ ] **Step 1: Update .env**

```bash
cd trading

# Backup old .env
cp .env .env.sqlite-backup

# Update DATABASE_URL
sed -i '' 's|^# DATABASE_URL=postgresql|DATABASE_URL=postgresql|' .env
# (Or manually set DATABASE_URL to Postgres connection string)
```

- [ ] **Step 2: Test Python reads migrated data**

```bash
python3 << 'EOF'
import asyncio
from config import load_config
from storage.db import DatabaseConnection

async def test():
    config = load_config()
    db_conn = DatabaseConnection(config)
    db = await db_conn.connect()

    # Query migrated data
    count = await db.fetchval("SELECT COUNT(*) FROM tracked_positions")
    print(f"✅ tracked_positions: {count} rows")

    sample = await db.fetchrow("SELECT * FROM agent_registry LIMIT 1")
    if sample:
        print(f"✅ agent_registry sample: {sample['name']}")

    await db_conn.close()

asyncio.run(test())
EOF
```

Expected: Shows data from PostgreSQL

- [ ] **Step 3: Run Python tests (should still pass)**

```bash
cd trading

# Tests use SQLite (config.db_path), unaffected by DATABASE_URL
python3 -m pytest tests/ -x
```

Expected: All tests pass (tests use SQLite, not Postgres)

- [ ] **Step 4: Test write operation**

```bash
python3 << 'EOF'
import asyncio
from config import load_config
from storage.db import DatabaseConnection

async def test():
    config = load_config()
    db_conn = DatabaseConnection(config)
    db = await db_conn.connect()

    # Insert test row
    await db.execute("""
        INSERT INTO opportunities (id, agent_name, symbol, signal, confidence, reasoning, status, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
    """, 'test-opp-1', 'pytest', 'AAPL', 'buy', 0.85, 'Test opportunity', 'pending')

    # Verify inserted
    result = await db.fetchrow("SELECT * FROM opportunities WHERE id = $1", 'test-opp-1')
    print(f"✅ Write successful: {result['symbol']}")

    # Cleanup
    await db.execute("DELETE FROM opportunities WHERE id = $1", 'test-opp-1')

    await db_conn.close()

asyncio.run(test())
EOF
```

Expected: `✅ Write successful: AAPL`

- [ ] **Step 5: Commit Postgres switchover**

```bash
git add trading/.env
git commit -m "feat(db): switch Python trading service to PostgreSQL

Changes:
- DATABASE_URL now points to Supabase Postgres
- Reads migrated data successfully
- Write operations work
- Tests still pass (use SQLite)

SQLite backup preserved at trading/.env.sqlite-backup"
```

---

## Acceptance Criteria

Phase 2 is **complete** when:

- [x] Schema drift audit documented (Task 1)
- [x] Postgres schema reconciled (Task 2)
  - migrations.py includes is_claimed, claimed_at, claimed_by, sequencing
- [x] Laravel migration generated from Postgres source (Task 3)
- [x] PostgreSQL connection configured for both services (Task 4)
- [x] Python's run_migrations() disabled (Task 5)
- [x] Laravel migration ran successfully - 45 tables created (Task 6)
- [x] Data migration script complete - all 43 tables (Tasks 7-8)
- [x] Verification passed - all row counts match (Task 9)
- [x] Python switched to Postgres - reads/writes work (Task 10)

**Final checklist:**

```bash
# All 45 tables exist
psql "$DATABASE_URL" -c "\dt" | wc -l  # Should be 45+

# Data migrated
python3 scripts/verify-migration.py  # All ✅

# Python uses Postgres
grep DATABASE_URL trading/.env  # Should be postgresql://

# Tests still pass
cd trading && python3 -m pytest tests/ -x  # All pass

# migrations.py archived
ls -la trading/storage/migrations.py*  # .deprecated exists
```

---

## Rollback Procedure

If issues found:

1. **Restore SQLite connection:**
   ```bash
   cp trading/.env.sqlite-backup trading/.env
   ```

2. **Rollback Laravel migration:**
   ```bash
   cd api
   php artisan migrate:rollback
   ```

3. **Drop Postgres tables:**
   ```bash
   psql "$DATABASE_URL" << 'EOF'
   DROP SCHEMA public CASCADE;
   CREATE SCHEMA public;
   EOF
   ```

4. **Investigate root cause before retry**

---

## Next Steps

After Phase 2 completes:
1. Begin Phase 3: Redis Streams Event Bus (Week 6)
2. Archive SQLite database: `mv trading/data.db trading/data.db.archived`
3. Update CI to use Postgres for integration tests

**Deliverable:** Commit "feat(db): Phase 2 complete - database consolidated to PostgreSQL"
