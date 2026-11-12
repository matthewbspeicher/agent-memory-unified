"""Every INSERT OR REPLACE must translate to a PostgreSQL conflict key that exists.

SQLite replaces on whichever unique key the new row collides with. PostgreSQL
needs the key named, and the facade guesses the first listed column unless the
table is registered. A wrong guess fails only at run time, on PostgreSQL.
"""

import re
import sqlite3
from pathlib import Path

import pytest

from storage.db import _INIT_DDL
from storage.postgres import PostgresDB

TRADING = Path(__file__).resolve().parents[3]
UPSERT = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO\s+([\w.]+)\s*\(([^)]*)\)", re.IGNORECASE
)
SKIP = ("tests", "venv", ".venv", "scratch", "node_modules")


def upserts():
    """(file, table, first column or None when the list is built at run time)."""
    found = []
    for path in sorted(TRADING.rglob("*.py")):
        relative = path.relative_to(TRADING)
        if relative.parts[0] in SKIP or relative.as_posix() == "storage/postgres.py":
            continue
        for table, columns in UPSERT.findall(path.read_text()):
            first = columns.split(",")[0].strip()
            static = re.fullmatch(r"\w+", first) is not None
            found.append((relative.as_posix(), table.split(".")[-1], first if static else None))
    return found


@pytest.fixture(scope="module")
def unique_keys():
    """table -> the column sets SQLite would replace on, from the engine's DDL."""
    db = sqlite3.connect(":memory:")
    db.executescript(_INIT_DDL)
    keys = {}
    for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        info = db.execute(f"PRAGMA table_info({table})").fetchall()
        primary = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]]
        found = [frozenset(primary)] if primary else []
        for index in db.execute(f"PRAGMA index_list({table})").fetchall():
            if index[2]:  # unique
                columns = db.execute(f"PRAGMA index_info({index[1]})").fetchall()
                found.append(frozenset(row[2] for row in columns))
        keys[table] = found
    return keys


def test_there_are_upserts_to_check():
    assert len(upserts()) > 15


@pytest.mark.parametrize("file, table, first", upserts())
def test_upsert_conflict_key_is_a_unique_key_of_the_table(file, table, first, unique_keys):
    if table not in unique_keys:
        pytest.skip(f"{table} is not created by the engine DDL")
    registered = PostgresDB._CONFLICT_KEYS.get(table)
    assert registered or first, (
        f"{file}: {table} builds its column list at run time, so its key must be"
        " registered in PostgresDB._CONFLICT_KEYS"
    )
    target = frozenset(registered or [first])
    assert target in unique_keys[table], (
        f"{file}: ON CONFLICT ({', '.join(sorted(target))}) is not a unique key of"
        f" {table}; its keys are {[sorted(k) for k in unique_keys[table]]}"
    )


def test_every_registered_key_is_a_unique_key(unique_keys):
    for table, columns in PostgresDB._CONFLICT_KEYS.items():
        assert frozenset(columns) in unique_keys[table], table


def test_the_registered_key_is_used_whatever_column_comes_first():
    sql = PostgresDB._translate(
        "INSERT OR REPLACE INTO bittensor_miner_rankings (miner_hotkey, symbol, hybrid_score)"
        " VALUES (?, ?, ?)"
    )
    assert "ON CONFLICT (miner_hotkey, symbol) DO UPDATE SET hybrid_score=EXCLUDED.hybrid_score" in sql
    sql = PostgresDB._translate(
        "INSERT OR REPLACE INTO trade_analytics (net_pnl, tracked_position_id) VALUES (?, ?)"
    )
    assert "ON CONFLICT (tracked_position_id) DO UPDATE SET net_pnl=EXCLUDED.net_pnl" in sql
