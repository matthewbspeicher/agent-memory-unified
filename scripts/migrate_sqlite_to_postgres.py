#!/usr/bin/env python3
"""
Data Migration Script: SQLite → PostgreSQL
Migrates all data from stock-trading-api SQLite database to unified PostgreSQL database.

Usage:
    python migrate_sqlite_to_postgres.py [--dry-run] [--table TABLE_NAME]

Options:
    --dry-run       Show what would be migrated without actually inserting data
    --table NAME    Migrate only the specified table
    --force         Skip confirmation prompts
"""

import os
import sys
import sqlite3
import asyncio
import asyncpg
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
from dateutil import parser as dateutil_parser
import argparse

# Source SQLite database
SQLITE_PATH = "/opt/homebrew/var/www/stock-trading-api/python/data.db"

# Target PostgreSQL connection (from .env)
POSTGRES_URL = "postgresql://postgres.tcumvviwzfernfoofwzh:H011y.w01151@aws-1-us-east-1.pooler.supabase.com:6543/postgres"

# Tables to migrate (all 29 tables from schema)
ALL_TABLES = [
    "agent_overrides",
    "agent_remembr_map",
    "agent_stages",
    "backtest_results",
    "consensus_votes",
    "convergence_syntheses",
    "daily_briefs",
    "execution_quality",
    "external_balances",
    "external_positions",
    "leaderboard_cache",
    "llm_lessons",
    "llm_prompt_versions",
    "opportunities",
    "opportunity_snapshots",
    "paper_accounts",
    "paper_orders",
    "paper_positions",
    "performance_snapshots",
    "position_exit_rules",
    "risk_events",
    "tournament_audit_log",
    "tournament_rounds",
    "tournament_variants",
    "tracked_positions",
    "trade_autopsies",
    "trades",
    "trust_events",
    "whatsapp_sessions",
]


class MigrationStats:
    def __init__(self):
        self.tables_processed = 0
        self.tables_skipped = 0
        self.rows_migrated = 0
        self.errors: List[str] = []
        self.start_time = datetime.now()

    def add_migrated(self, table: str, count: int):
        self.tables_processed += 1
        self.rows_migrated += count
        print(f"  ✓ {table}: {count} rows migrated")

    def add_skipped(self, table: str, reason: str):
        self.tables_skipped += 1
        print(f"  - {table}: {reason}")

    def add_error(self, table: str, error: str):
        self.errors.append(f"{table}: {error}")
        print(f"  ✗ {table}: ERROR - {error}")

    def report(self):
        duration = (datetime.now() - self.start_time).total_seconds()
        print("\n" + "=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)
        print(f"Duration:         {duration:.2f}s")
        print(f"Tables processed: {self.tables_processed}")
        print(f"Tables skipped:   {self.tables_skipped}")
        print(f"Rows migrated:    {self.rows_migrated}")
        print(f"Errors:           {len(self.errors)}")
        if self.errors:
            print("\nErrors encountered:")
            for error in self.errors:
                print(f"  • {error}")
        print("=" * 70)


def get_sqlite_connection():
    """Connect to source SQLite database."""
    if not Path(SQLITE_PATH).exists():
        print(f"Error: SQLite database not found at {SQLITE_PATH}")
        sys.exit(1)
    return sqlite3.connect(SQLITE_PATH)


async def get_postgres_connection():
    """Connect to target PostgreSQL database."""
    # Disable statement cache for pgbouncer compatibility
    return await asyncpg.connect(POSTGRES_URL, statement_cache_size=0)


def get_sqlite_row_count(conn: sqlite3.Connection, table: str) -> int:
    """Get row count from SQLite table."""
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    return cursor.fetchone()[0]


def get_sqlite_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Get column names from SQLite table."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def convert_datetime_strings(value: Any) -> Any:
    """Convert datetime strings to datetime objects."""
    if not isinstance(value, str):
        return value

    # Common datetime column patterns
    datetime_patterns = ['_at', 'date', 'time']

    # Try parsing as datetime
    try:
        # Check if it looks like a datetime string
        if any(c in value for c in ['-', ':', ' ', 'T']):
            # Attempt to parse
            dt = dateutil_parser.parse(value)
            return dt
    except (ValueError, TypeError, dateutil_parser.ParserError):
        pass

    return value


def fetch_sqlite_data(conn: sqlite3.Connection, table: str) -> List[Dict[str, Any]]:
    """Fetch all rows from SQLite table as dictionaries."""
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table}")
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    # Convert rows to dicts and parse datetime strings
    result = []
    for row in rows:
        row_dict = dict(zip(columns, row))
        # Convert datetime strings in columns ending with _at or containing date/time
        for col_name, value in row_dict.items():
            if value is not None and any(pattern in col_name.lower() for pattern in ['_at', 'date', 'time']):
                row_dict[col_name] = convert_datetime_strings(value)
        result.append(row_dict)

    return result


async def insert_postgres_batch(
    pg_conn: asyncpg.Connection,
    table: str,
    rows: List[Dict[str, Any]],
    dry_run: bool = False
) -> int:
    """Insert batch of rows into PostgreSQL table."""
    if not rows:
        return 0

    if dry_run:
        print(f"    [DRY RUN] Would insert {len(rows)} rows into {table}")
        return len(rows)

    # Build INSERT statement
    columns = list(rows[0].keys())
    placeholders = ", ".join([f"${i+1}" for i in range(len(columns))])
    column_names = ", ".join(columns)

    insert_sql = f"""
        INSERT INTO {table} ({column_names})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
    """

    inserted = 0
    for row in rows:
        try:
            values = [row[col] for col in columns]
            await pg_conn.execute(insert_sql, *values)
            inserted += 1
        except Exception as e:
            print(f"      Warning: Failed to insert row in {table}: {e}")
            # Continue with other rows
            continue

    return inserted


async def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: asyncpg.Connection,
    table: str,
    stats: MigrationStats,
    dry_run: bool = False
):
    """Migrate a single table from SQLite to PostgreSQL."""
    try:
        # Check if table has data
        row_count = get_sqlite_row_count(sqlite_conn, table)

        if row_count == 0:
            stats.add_skipped(table, "no data")
            return

        print(f"\n  Migrating {table} ({row_count} rows)...")

        # Fetch data from SQLite
        rows = fetch_sqlite_data(sqlite_conn, table)

        if not rows:
            stats.add_skipped(table, "no rows fetched")
            return

        # Insert into PostgreSQL
        inserted = await insert_postgres_batch(pg_conn, table, rows, dry_run)

        stats.add_migrated(table, inserted)

    except Exception as e:
        stats.add_error(table, str(e))


async def verify_postgres_schema(pg_conn: asyncpg.Connection, tables: List[str]) -> tuple[bool, List[str]]:
    """Verify which tables exist in PostgreSQL. Returns (success, valid_tables)."""
    print("\nVerifying PostgreSQL schema...")

    result = await pg_conn.fetch("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
    """)

    existing_tables = {row['tablename'] for row in result}
    missing_tables = set(tables) - existing_tables
    valid_tables = [t for t in tables if t in existing_tables]

    if missing_tables:
        print(f"  ! Skipping {len(missing_tables)} missing tables: {', '.join(sorted(missing_tables))}")

    if valid_tables:
        print(f"  ✓ Found {len(valid_tables)} matching tables in PostgreSQL")
        return True, valid_tables
    else:
        print(f"  ✗ No matching tables found in PostgreSQL")
        return False, []


async def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated")
    parser.add_argument("--table", type=str, help="Migrate only this table")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    args = parser.parse_args()

    print("=" * 70)
    print("SQLite → PostgreSQL Data Migration")
    print("=" * 70)
    print(f"Source: {SQLITE_PATH}")
    print(f"Target: {POSTGRES_URL.split('@')[1].split('/')[0]}...")
    print(f"Mode:   {'DRY RUN' if args.dry_run else 'LIVE MIGRATION'}")
    print("=" * 70)

    # Determine which tables to migrate
    tables_to_migrate = [args.table] if args.table else ALL_TABLES

    # Connect to databases
    print("\nConnecting to databases...")
    sqlite_conn = get_sqlite_connection()
    print("  ✓ Connected to SQLite")

    pg_conn = await get_postgres_connection()
    print("  ✓ Connected to PostgreSQL")

    # Verify schema and get valid tables
    schema_ok, valid_tables = await verify_postgres_schema(pg_conn, tables_to_migrate)
    if not schema_ok:
        print("\n✗ No valid tables to migrate.")
        await pg_conn.close()
        sqlite_conn.close()
        sys.exit(1)

    # Update tables to migrate to only include valid ones
    tables_to_migrate = valid_tables

    # Show data summary
    print("\nSource data summary:")
    total_rows = 0
    non_empty_tables = []
    for table in sorted(tables_to_migrate):
        count = get_sqlite_row_count(sqlite_conn, table)
        if count > 0:
            print(f"  {table}: {count} rows")
            total_rows += count
            non_empty_tables.append(table)

    if total_rows == 0:
        print("  No data to migrate.")
        await pg_conn.close()
        sqlite_conn.close()
        return

    print(f"\nTotal: {len(non_empty_tables)} tables with {total_rows} rows")

    # Confirmation
    if not args.dry_run and not args.force:
        response = input("\nProceed with migration? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Migration cancelled.")
            await pg_conn.close()
            sqlite_conn.close()
            return

    # Migrate tables
    print("\nStarting migration...\n")
    stats = MigrationStats()

    for table in sorted(tables_to_migrate):
        await migrate_table(sqlite_conn, pg_conn, table, stats, args.dry_run)

    # Cleanup
    await pg_conn.close()
    sqlite_conn.close()

    # Report
    stats.report()

    if stats.errors:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
